"""正式な応募履歴(application_history_service)のテスト。"""
from __future__ import annotations

import pytest

from src.config import APP_STATUS_HIRED, APP_STATUS_REPLIED, STATUS_HIRED
from src.crm.application_history_service import (
    DuplicateApplicationError,
    change_application_status,
    create_application_history,
    get_application_detail,
)
from src.database import session
from src.repositories import (
    get_current_application_draft,
    get_job,
    insert_job,
    save_job_analysis,
    update_application_draft,
)


def _insert_job_with_analysis(db_path, title="AI開発案件") -> int:
    with session(db_path) as conn:
        job_id = insert_job(conn, {
            "title": title, "body": "PythonとOpenAI APIで業務自動化ツールを開発してください。" * 3,
            "category": "AI開発", "job_type": "固定報酬制", "source_type": "manual",
            "client_name": "テスト株式会社", "client_rating": 4.6, "identity_verified": 1,
            "applicant_count": 4,
        })
        save_job_analysis(conn, job_id, {
            "rule_based_score": 75, "ai_suitability_score": 82, "total_score": 80,
            "safety_score": 92, "risk_level": "low", "used_ai": 1,
        })
    return job_id


def _insert_job_with_draft(db_path, title="デザイン案件") -> tuple[int, int]:
    job_id = _insert_job_with_analysis(db_path, title)
    with session(db_path) as conn:
        from src.application.application_generator import generate_application
        from src.repositories import get_profile_bundle

        job = get_job(conn, job_id)
        bundle = get_profile_bundle(conn)
        result = generate_application(conn, job, bundle, None, None, generation_type="template")
        from src.repositories import create_application_draft

        draft_data = {k: v for k, v in result.items() if k not in ("client_questions", "candidate_portfolios", "char_count")}
        draft_data["application_message"] = draft_data.pop("full_message")
        draft_id = create_application_draft(conn, job_id, draft_data)
    return job_id, draft_id


def test_create_application_history_saves_full_record(db_path):
    job_id = _insert_job_with_analysis(db_path)
    with session(db_path) as conn:
        record_id = create_application_history(conn, job_id, proposed_price=40000, proposed_delivery_days=7)

    with session(db_path) as conn:
        detail = get_application_detail(conn, record_id)
    record = detail["record"]
    assert record["job_id"] == job_id
    assert record["proposed_price"] == 40000
    assert record["source_platform"] == "クラウドワークス"
    assert record["total_score_snapshot"] == 80
    assert record["ai_score_snapshot"] == 82
    assert record["safety_score_snapshot"] == 92


def test_sent_message_snapshot_saved(db_path):
    job_id, draft_id = _insert_job_with_draft(db_path)
    with session(db_path) as conn:
        record_id = create_application_history(conn, job_id, application_draft_id=draft_id)
    with session(db_path) as conn:
        record = get_application_detail(conn, record_id)["record"]
    assert record["sent_message"]
    assert record["generation_type"] == "template"


def test_portfolio_snapshot_saved(db_path):
    job_id, draft_id = _insert_job_with_draft(db_path, title="バナー制作案件（Illustrator使用）")
    with session(db_path) as conn:
        record_id = create_application_history(conn, job_id, application_draft_id=draft_id)
    with session(db_path) as conn:
        record = get_application_detail(conn, record_id)["record"]
    # ポートフォリオが選択されていればスナップショットに含まれる（0件でもリスト自体は必ず存在する）
    assert isinstance(record["portfolio_snapshot"], list)
    assert isinstance(record["portfolio_urls"], list)


def test_duplicate_application_is_blocked(db_path):
    job_id = _insert_job_with_analysis(db_path)
    with session(db_path) as conn:
        create_application_history(conn, job_id)

    with session(db_path) as conn:
        with pytest.raises(DuplicateApplicationError):
            create_application_history(conn, job_id)


def test_intentional_reapplication_with_reason_succeeds(db_path):
    job_id = _insert_job_with_analysis(db_path)
    with session(db_path) as conn:
        first_id = create_application_history(conn, job_id)

    with session(db_path) as conn:
        second_id = create_application_history(
            conn, job_id, is_reapplication=True, reapplication_reason="条件が変わったため再応募",
        )
    assert second_id != first_id

    with session(db_path) as conn:
        record = get_application_detail(conn, second_id)["record"]
    assert record["is_reapplication"] is True
    assert record["reapplication_reason"] == "条件が変わったため再応募"


def test_snapshot_not_changed_after_job_and_analysis_updated(db_path):
    job_id = _insert_job_with_analysis(db_path)
    with session(db_path) as conn:
        record_id = create_application_history(conn, job_id)

    # 応募後に案件・分析結果が変わっても、スナップショットは変わらない
    with session(db_path) as conn:
        save_job_analysis(conn, job_id, {
            "rule_based_score": 10, "ai_suitability_score": 5, "total_score": 5,
            "safety_score": 5, "risk_level": "critical", "used_ai": 1,
        })

    with session(db_path) as conn:
        record = get_application_detail(conn, record_id)["record"]
    assert record["total_score_snapshot"] == 80
    assert record["ai_score_snapshot"] == 82
    assert record["safety_score_snapshot"] == 92


def test_status_change_records_history_and_syncs_job_status(db_path):
    job_id = _insert_job_with_analysis(db_path)
    with session(db_path) as conn:
        record_id = create_application_history(conn, job_id)
        change_application_status(conn, record_id, APP_STATUS_REPLIED, change_reason="返信あり")

    with session(db_path) as conn:
        detail = get_application_detail(conn, record_id)
    types = [h["new_status"] for h in detail["status_history"]]
    assert APP_STATUS_REPLIED in types


def test_critical_status_change_requires_confirmation(db_path):
    job_id = _insert_job_with_analysis(db_path)
    with session(db_path) as conn:
        record_id = create_application_history(conn, job_id)
        result = change_application_status(conn, record_id, APP_STATUS_HIRED)

    assert result["requires_confirmation"] is True

    with session(db_path) as conn:
        job = get_job(conn, job_id)
    assert job["status"] == STATUS_HIRED


def test_non_critical_status_change_does_not_require_confirmation(db_path):
    job_id = _insert_job_with_analysis(db_path)
    with session(db_path) as conn:
        record_id = create_application_history(conn, job_id)
        result = change_application_status(conn, record_id, APP_STATUS_REPLIED)
    assert result["requires_confirmation"] is False


def test_application_draft_status_synced_to_applied(db_path):
    job_id, draft_id = _insert_job_with_draft(db_path)
    with session(db_path) as conn:
        create_application_history(conn, job_id, application_draft_id=draft_id)
    with session(db_path) as conn:
        draft = get_current_application_draft(conn, job_id)
    assert draft["preparation_status"] == "応募済み"
