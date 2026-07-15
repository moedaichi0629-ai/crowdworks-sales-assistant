"""本日の応募候補自動選定(candidate_selector)のテスト。"""
from __future__ import annotations

from src.config import CANDIDATE_STATUS_ACTIVE, STATUS_APPLIED
from src.daily.candidate_selector import select_daily_candidates
from src.daily.daily_dashboard_service import skip_candidate
from src.daily.goal_service import save_daily_goal
from src.database import session
from src.repositories import (
    get_daily_candidate_by_job,
    get_daily_candidates,
    insert_job,
    save_job_analysis,
    update_status_bulk,
)

TARGET_DATE = "2026-07-15"


def _insert(db_path, title, body, category="AI開発", **job_overrides):
    job_overrides.setdefault("applicant_count", 5)
    job_overrides.setdefault("client_rating", 4.0)
    job_overrides.setdefault("identity_verified", 1)
    job_overrides.setdefault("deadline", "2026-08-01")
    job_overrides.setdefault("published_at", "2026-07-15 08:00:00")
    with session(db_path) as conn:
        job_id = insert_job(conn, {
            "title": title, "body": body, "category": category, "job_type": "固定報酬制",
            "source_type": "manual", **job_overrides,
        })
    return job_id


def _analyze(db_path, job_id, **overrides):
    data = {
        "rule_based_score": 70, "ai_suitability_score": 75, "total_score": 80,
        "safety_score": 90, "risk_level": "low", "used_ai": 0, "budget_evaluation": "good",
        "missing_skills": [],
    }
    data.update(overrides)
    with session(db_path) as conn:
        save_job_analysis(conn, job_id, data)


def _active_ids(candidates):
    return {c["job_id"] for c in candidates if c["candidate_status"] == CANDIDATE_STATUS_ACTIVE}


def test_candidates_ranked_by_total_score(db_path):
    high_id = _insert(db_path, "高スコア案件", "PythonでAPI連携ツールを開発してください。" * 3)
    _analyze(db_path, high_id, total_score=95)
    low_id = _insert(db_path, "低スコア案件", "PythonでAPI連携ツールを開発してください。" * 3)
    _analyze(db_path, low_id, total_score=72)

    with session(db_path) as conn:
        save_daily_goal(conn, TARGET_DATE, {
            "target_count": 2, "ai_development_target": 2, "design_target": 0, "other_target": 0,
        })
        select_daily_candidates(conn, TARGET_DATE)
        candidates = get_daily_candidates(conn, TARGET_DATE)

    active = [c for c in candidates if c["candidate_status"] == CANDIDATE_STATUS_ACTIVE]
    assert active[0]["job_id"] == high_id


def test_low_safety_score_excluded(db_path):
    ok_id = _insert(db_path, "安全な案件", "PythonでAPI連携ツールを開発してください。" * 3)
    _analyze(db_path, ok_id, safety_score=90)
    unsafe_id = _insert(db_path, "安全度が低い案件", "PythonでAPI連携ツールを開発してください。" * 3)
    _analyze(db_path, unsafe_id, safety_score=50)

    with session(db_path) as conn:
        select_daily_candidates(conn, TARGET_DATE)
        active = _active_ids(get_daily_candidates(conn, TARGET_DATE))

    assert ok_id in active
    assert unsafe_id not in active


def test_critical_risk_excluded(db_path):
    danger_id = _insert(db_path, "危険案件", "初期費用として登録費用が必要です。教材購入をお願いします。" * 3)
    _analyze(db_path, danger_id, risk_level="critical", safety_score=20)

    with session(db_path) as conn:
        select_daily_candidates(conn, TARGET_DATE)
        active = _active_ids(get_daily_candidates(conn, TARGET_DATE))

    assert danger_id not in active


def test_applied_job_excluded(db_path):
    applied_id = _insert(db_path, "応募済み案件", "PythonでAPI連携ツールを開発してください。" * 3)
    _analyze(db_path, applied_id)
    with session(db_path) as conn:
        update_status_bulk(conn, [applied_id], STATUS_APPLIED)
        select_daily_candidates(conn, TARGET_DATE)
        candidates = get_daily_candidates(conn, TARGET_DATE)
    assert all(c["job_id"] != applied_id for c in candidates)


def test_skipped_job_excluded_from_future_dates(db_path):
    job_id = _insert(db_path, "見送り対象案件", "PythonでAPI連携ツールを開発してください。" * 3)
    _analyze(db_path, job_id)

    with session(db_path) as conn:
        select_daily_candidates(conn, "2026-07-14")
        candidate = get_daily_candidate_by_job(conn, "2026-07-14", job_id)
        skip_candidate(conn, candidate["id"])

    with session(db_path) as conn:
        select_daily_candidates(conn, "2026-07-15")
        candidates = get_daily_candidates(conn, "2026-07-15")
    assert all(c["job_id"] != job_id for c in candidates)


def test_expired_deadline_excluded(db_path):
    job_id = _insert(db_path, "期限切れ案件", "PythonでAPI連携ツールを開発してください。" * 3, deadline="2026-07-01")
    _analyze(db_path, job_id)
    with session(db_path) as conn:
        select_daily_candidates(conn, TARGET_DATE)
        candidates = get_daily_candidates(conn, TARGET_DATE)
    assert all(c["job_id"] != job_id for c in candidates)


def test_category_group_allocation(db_path):
    ai_id = _insert(db_path, "AI開発案件", "PythonとOpenAI APIで業務自動化ツールを開発してください。" * 3, category="AI開発")
    _analyze(db_path, ai_id)
    design_id = _insert(db_path, "バナー制作案件", "Illustratorでバナー・SNS投稿画像を制作してください。" * 3, category="デザイン")
    _analyze(db_path, design_id)
    other_id = _insert(db_path, "データ入力案件", "スプレッドシートへのデータ入力・リサーチをお願いします。" * 3, category="その他")
    _analyze(db_path, other_id)

    with session(db_path) as conn:
        save_daily_goal(conn, TARGET_DATE, {
            "target_count": 3, "ai_development_target": 1, "design_target": 1, "other_target": 1,
        })
        select_daily_candidates(conn, TARGET_DATE)
        candidates = get_daily_candidates(conn, TARGET_DATE)

    active = {c["job_id"]: c["category_group"] for c in candidates if c["candidate_status"] == CANDIDATE_STATUS_ACTIVE}
    assert active.get(ai_id) == "AI・開発"
    assert active.get(design_id) == "デザイン"
    assert active.get(other_id) == "その他"


def test_shortage_backfilled_from_other_category(db_path):
    ai_id1 = _insert(db_path, "AI開発案件1", "PythonとOpenAI APIで業務自動化ツールを開発してください。" * 3, category="AI開発")
    _analyze(db_path, ai_id1)
    ai_id2 = _insert(db_path, "AI開発案件2", "PythonとOpenAI APIで業務自動化ツールを開発してください。" * 3, category="AI開発")
    _analyze(db_path, ai_id2)
    # デザイン枠は該当案件が0件のため不足する → AI・開発から補充されるはず

    with session(db_path) as conn:
        save_daily_goal(conn, TARGET_DATE, {
            "target_count": 2, "ai_development_target": 1, "design_target": 1, "other_target": 0,
        })
        select_daily_candidates(conn, TARGET_DATE)
        active = _active_ids(get_daily_candidates(conn, TARGET_DATE))

    assert active == {ai_id1, ai_id2}


def test_shortage_not_backfilled_with_unsafe_jobs(db_path):
    ok_id = _insert(db_path, "安全な案件", "PythonでAPI連携ツールを開発してください。" * 3, category="AI開発")
    _analyze(db_path, ok_id)
    unsafe_id = _insert(db_path, "危険な案件", "初期費用として登録費用が必要です。教材購入をお願いします。" * 3, category="AI開発")
    _analyze(db_path, unsafe_id, risk_level="critical", safety_score=10)

    with session(db_path) as conn:
        save_daily_goal(conn, TARGET_DATE, {
            "target_count": 5, "ai_development_target": 5, "design_target": 0, "other_target": 0,
        })
        select_daily_candidates(conn, TARGET_DATE)
        active = _active_ids(get_daily_candidates(conn, TARGET_DATE))

    assert ok_id in active
    assert unsafe_id not in active


def test_no_duplicate_candidate_rows_for_same_job(db_path):
    job_id = _insert(db_path, "重複防止テスト案件", "PythonでAPI連携ツールを開発してください。" * 3)
    _analyze(db_path, job_id)

    with session(db_path) as conn:
        select_daily_candidates(conn, TARGET_DATE)
        select_daily_candidates(conn, TARGET_DATE)  # 再選定を2回実行しても重複しないこと
        count = conn.execute(
            "SELECT COUNT(*) FROM daily_candidates WHERE target_date = ? AND job_id = ?", (TARGET_DATE, job_id),
        ).fetchone()[0]
    assert count == 1
