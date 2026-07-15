"""面談管理(interview_service)のテスト。"""
from __future__ import annotations

from src.config import APP_STATUS_INTERVIEW_DONE, APP_STATUS_INTERVIEW_SCHEDULED
from src.crm.application_history_service import create_application_history, get_application_detail
from src.crm.interview_service import (
    cancel_interview,
    complete_interview,
    confirm_interview,
    create_interview,
    get_interviews_for_record,
    reschedule_interview,
)
from src.database import session
from src.repositories import insert_job


def _insert_record(db_path) -> int:
    with session(db_path) as conn:
        job_id = insert_job(conn, {"title": "面談テスト案件", "source_type": "manual"})
        return create_application_history(conn, job_id)


def test_create_interview(db_path):
    record_id = _insert_record(db_path)
    with session(db_path) as conn:
        interview_id = create_interview(conn, record_id, title="初回面談", scheduled_start="2026-07-20 14:00:00")

    with session(db_path) as conn:
        interviews = get_interviews_for_record(conn, record_id)
    assert len(interviews) == 1
    assert interviews[0]["id"] == interview_id
    assert interviews[0]["status"] == "調整中"


def test_confirm_interview_syncs_application_status(db_path):
    record_id = _insert_record(db_path)
    with session(db_path) as conn:
        interview_id = create_interview(conn, record_id, scheduled_start="2026-07-20 14:00:00")
        confirm_interview(conn, interview_id)

    with session(db_path) as conn:
        detail = get_application_detail(conn, record_id)
    assert detail["record"]["application_status"] == APP_STATUS_INTERVIEW_SCHEDULED
    assert detail["interviews"][0]["status"] == "確定"


def test_reschedule_interview_changes_datetime(db_path):
    record_id = _insert_record(db_path)
    with session(db_path) as conn:
        interview_id = create_interview(conn, record_id, scheduled_start="2026-07-20 14:00:00")
        reschedule_interview(conn, interview_id, "2026-07-22 10:00:00")

    with session(db_path) as conn:
        interviews = get_interviews_for_record(conn, record_id)
    assert interviews[0]["scheduled_start"] == "2026-07-22 10:00:00"
    assert interviews[0]["status"] == "調整中"


def test_complete_interview_saves_result_and_syncs_status(db_path):
    record_id = _insert_record(db_path)
    with session(db_path) as conn:
        interview_id = create_interview(conn, record_id, scheduled_start="2026-07-20 14:00:00")
        complete_interview(conn, interview_id, result="好感触でした", next_step="採用可否連絡待ち")

    with session(db_path) as conn:
        detail = get_application_detail(conn, record_id)
    assert detail["interviews"][0]["status"] == "実施済み"
    assert detail["interviews"][0]["result"] == "好感触でした"
    assert detail["record"]["application_status"] == APP_STATUS_INTERVIEW_DONE


def test_cancel_interview(db_path):
    record_id = _insert_record(db_path)
    with session(db_path) as conn:
        interview_id = create_interview(conn, record_id, scheduled_start="2026-07-20 14:00:00")
        cancel_interview(conn, interview_id)

    with session(db_path) as conn:
        interviews = get_interviews_for_record(conn, record_id)
    assert interviews[0]["status"] == "キャンセル"


def test_cancel_interview_no_show(db_path):
    record_id = _insert_record(db_path)
    with session(db_path) as conn:
        interview_id = create_interview(conn, record_id, scheduled_start="2026-07-20 14:00:00")
        cancel_interview(conn, interview_id, no_show=True)

    with session(db_path) as conn:
        interviews = get_interviews_for_record(conn, record_id)
    assert interviews[0]["status"] == "無断キャンセル"
