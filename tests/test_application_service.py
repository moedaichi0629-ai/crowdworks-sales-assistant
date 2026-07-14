"""営業文サービス層(application_service / version_service / checklist_service)のテスト。"""
from __future__ import annotations

from src.application.application_generator import GenerationBlockedError
from src.application.application_service import (
    copy_application,
    edit_with_instruction,
    generate_for_job,
    manual_edit_application,
    run_bulk_generation,
)
from src.application.checklist_service import CHECKLIST_LABELS, get_checklist, save_checklist
from src.application.version_service import get_version_history, revert_to_version
from src.database import session
from src.repositories import get_current_application_draft, insert_job


def _insert_job(db_path, title="AI開発案件", body=None) -> int:
    job = {
        "title": title,
        "body": body or "AIチャットボットを開発してください。DifyまたはOpenAI APIの使用経験があれば教えてください。",
        "job_type": "固定報酬制", "category": "AI開発", "budget_min": 30000, "budget_max": 50000,
        "budget_text": "30000円〜50000円", "applicant_count": 2, "client_name": "テスト会社",
        "client_rating": 4.5, "identity_verified": 1, "source_type": "manual",
    }
    with session(db_path) as conn:
        return insert_job(conn, job)


def test_generate_for_job_creates_draft(db_path):
    job_id = _insert_job(db_path)
    with session(db_path) as conn:
        result = generate_for_job(conn, job_id, force_template=True)
    assert result["draft_id"] is not None
    assert result["_from_cache"] is False


def test_regenerate_without_force_hits_cache(db_path):
    job_id = _insert_job(db_path)
    with session(db_path) as conn:
        first = generate_for_job(conn, job_id, force_template=True)
    with session(db_path) as conn:
        second = generate_for_job(conn, job_id, force_template=True)
    assert second["_from_cache"] is True
    assert second["draft_id"] == first["draft_id"]


def test_manual_edit_preserved_when_regenerating_without_force(db_path):
    job_id = _insert_job(db_path)
    with session(db_path) as conn:
        first = generate_for_job(conn, job_id, force_template=True)

    with session(db_path) as conn:
        manual_edit_application(conn, first["draft_id"], "手動で編集した営業文です。")

    with session(db_path) as conn:
        second = generate_for_job(conn, job_id, force_template=True)  # force_regenerate=False

    with session(db_path) as conn:
        draft = get_current_application_draft(conn, job_id)
    assert draft["application_message"] == "手動で編集した営業文です。"
    assert second["_from_cache"] is True


def test_force_regenerate_overwrites_and_records_version(db_path):
    job_id = _insert_job(db_path)
    with session(db_path) as conn:
        first = generate_for_job(conn, job_id, force_template=True)
    with session(db_path) as conn:
        manual_edit_application(conn, first["draft_id"], "編集前の内容")
    with session(db_path) as conn:
        generate_for_job(conn, job_id, force_template=True, force_regenerate=True)

    with session(db_path) as conn:
        history = get_version_history(conn, first["draft_id"])
    # 手動編集 + 再生成前保存 + 強制再生成後の記録、が積まれている
    assert len(history) >= 2
    types = [h["version_type"] for h in history]
    assert "manual_edit" in types


def test_revert_to_version_restores_message(db_path):
    job_id = _insert_job(db_path)
    with session(db_path) as conn:
        first = generate_for_job(conn, job_id, force_template=True)
        original_message = first["application_message"]

    with session(db_path) as conn:
        manual_edit_application(conn, first["draft_id"], "上書きされた内容")

    with session(db_path) as conn:
        history = get_version_history(conn, first["draft_id"])
        original_version = next(h for h in history if h["application_message"] == original_message)
        revert_to_version(conn, first["draft_id"], original_version["id"])

    with session(db_path) as conn:
        draft = get_current_application_draft(conn, job_id)
    assert draft["application_message"] == original_message


def test_edit_with_instruction_changes_length_type(db_path):
    job_id = _insert_job(db_path)
    with session(db_path) as conn:
        generate_for_job(conn, job_id, force_template=True, length_type="標準")

    with session(db_path) as conn:
        result = edit_with_instruction(conn, job_id, "短くする", force_template=True)
    assert result["length_type"] == "短文"


def test_copy_application_records_timestamp_without_changing_status(db_path):
    job_id = _insert_job(db_path)
    with session(db_path) as conn:
        first = generate_for_job(conn, job_id, force_template=True)
    with session(db_path) as conn:
        copy_application(conn, first["draft_id"])
    with session(db_path) as conn:
        draft = get_current_application_draft(conn, job_id)
    assert draft["copied_at"] is not None
    assert draft["preparation_status"] != "応募済み"


def test_checklist_all_checked_sets_ready_status(db_path):
    job_id = _insert_job(db_path)
    with session(db_path) as conn:
        first = generate_for_job(conn, job_id, force_template=True)

    with session(db_path) as conn:
        checklist = get_checklist(conn, first["draft_id"])
    assert all(v is False for v in checklist.values())

    with session(db_path) as conn:
        all_checked = save_checklist(conn, first["draft_id"], {f: True for f in CHECKLIST_LABELS})
    assert all_checked is True

    with session(db_path) as conn:
        draft = get_current_application_draft(conn, job_id)
    assert draft["preparation_status"] == "応募準備完了"


def test_checklist_partial_does_not_set_ready(db_path):
    job_id = _insert_job(db_path)
    with session(db_path) as conn:
        first = generate_for_job(conn, job_id, force_template=True)

    partial = {f: (i == 0) for i, f in enumerate(CHECKLIST_LABELS)}
    with session(db_path) as conn:
        all_checked = save_checklist(conn, first["draft_id"], partial)
    assert all_checked is False


def test_bulk_generation_counts_success_and_blocked(db_path):
    good_job_id = _insert_job(db_path, title="通常案件")
    with session(db_path) as conn:
        bad_job_id = insert_job(conn, {
            "title": "危険案件", "body": "初期費用として登録費用が必要です。教材購入をお願いします。",
            "source_type": "manual",
        })

    with session(db_path) as conn:
        summary = run_bulk_generation(conn, [good_job_id, bad_job_id], wait_seconds=0, force_template=True)

    assert summary["total"] == 2
    assert summary["success"] == 1
    assert summary["blocked"] == 1
