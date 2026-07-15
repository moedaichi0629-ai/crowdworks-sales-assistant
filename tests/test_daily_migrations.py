"""第4段階Part1: 日次応募目標・候補選定テーブルのマイグレーションのテスト。"""
from __future__ import annotations

from src.database import init_db, session
from src.repositories import (
    create_application_record,
    get_daily_candidates,
    insert_job,
    list_application_records_for_job,
    save_job_analysis,
    upsert_daily_candidate,
)


def test_migration_creates_daily_tables(db_path):
    with session(db_path) as conn:
        tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    expected = {"daily_application_goals", "daily_candidates", "application_records", "daily_selection_settings"}
    assert expected.issubset(tables)


def test_migration_is_idempotent(db_path):
    init_db(db_path)
    init_db(db_path)  # 例外が発生しないこと


def test_default_daily_selection_settings_seeded(db_path):
    with session(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM daily_selection_settings").fetchone()[0]
    assert count > 0


def test_existing_analysis_data_preserved_across_migration(db_path):
    with session(db_path) as conn:
        job_id = insert_job(conn, {"title": "既存案件", "source_type": "manual"})
        save_job_analysis(conn, job_id, {
            "rule_based_score": 70, "total_score": 75, "safety_score": 90, "risk_level": "low", "used_ai": 0,
        })

    init_db(db_path)  # マイグレーションを再実行

    with session(db_path) as conn:
        rows = conn.execute("SELECT total_score FROM job_analyses WHERE job_id = ?", (job_id,)).fetchall()
    assert any(r["total_score"] == 75 for r in rows)


def test_daily_candidate_can_be_saved(db_path):
    with session(db_path) as conn:
        job_id = insert_job(conn, {"title": "候補テスト案件", "source_type": "manual"})
        upsert_daily_candidate(conn, "2026-07-15", job_id, {
            "category_group": "AI・開発", "daily_priority_score": 80, "rank_number": 1,
            "selection_reasons": ["テスト理由"], "candidate_status": "候補",
        })

    with session(db_path) as conn:
        candidates = get_daily_candidates(conn, "2026-07-15")
    assert len(candidates) == 1
    assert candidates[0]["daily_priority_score"] == 80
    assert candidates[0]["selection_reasons"] == ["テスト理由"]


def test_application_record_can_be_saved(db_path):
    with session(db_path) as conn:
        job_id = insert_job(conn, {"title": "応募記録テスト案件", "source_type": "manual"})
        create_application_record(conn, {
            "job_id": job_id, "proposed_price": 30000, "proposed_delivery_days": 7,
        })

    with session(db_path) as conn:
        records = list_application_records_for_job(conn, job_id)
    assert len(records) == 1
    assert records[0]["application_status"] == "応募済み"
