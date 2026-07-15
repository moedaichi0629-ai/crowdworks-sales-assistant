"""クライアント返信管理(response_service)のテスト。"""
from __future__ import annotations

import datetime

from src.crm.application_history_service import create_application_history
from src.crm.response_service import (
    answer_response,
    get_overdue_responses,
    get_responses_for_record,
    get_unhandled_responses,
    record_response,
    update_response_status,
)
from src.database import session
from src.repositories import create_client_response, insert_job
from src.utils import now_jst_str


def _insert_record(db_path) -> int:
    with session(db_path) as conn:
        job_id = insert_job(conn, {"title": "返信テスト案件", "source_type": "manual"})
        return job_id


def test_record_response_sets_due_date(db_path):
    job_id = _insert_record(db_path)
    with session(db_path) as conn:
        record_id = create_application_history(conn, job_id)
        response_id = record_response(conn, record_id, "質問", "稼働時間を教えてください", target_hours=24)

    with session(db_path) as conn:
        responses = get_responses_for_record(conn, record_id)
    assert len(responses) == 1
    assert responses[0]["id"] == response_id
    assert responses[0]["response_due_at"] is not None
    assert responses[0]["response_status"] == "未対応"


def test_answer_response_marks_replied(db_path):
    job_id = _insert_record(db_path)
    with session(db_path) as conn:
        record_id = create_application_history(conn, job_id)
        response_id = record_response(conn, record_id, "質問", "稼働時間を教えてください")
        answer_response(conn, response_id, "週10時間ほど対応可能です")

    with session(db_path) as conn:
        responses = get_responses_for_record(conn, record_id)
    assert responses[0]["answer_body"] == "週10時間ほど対応可能です"
    assert responses[0]["response_status"] == "返信済み"
    assert responses[0]["answered_at"] is not None


def test_update_response_status(db_path):
    job_id = _insert_record(db_path)
    with session(db_path) as conn:
        record_id = create_application_history(conn, job_id)
        response_id = record_response(conn, record_id, "面談依頼", "面談可能でしょうか")
        update_response_status(conn, response_id, "回答案作成中")

    with session(db_path) as conn:
        responses = get_responses_for_record(conn, record_id)
    assert responses[0]["response_status"] == "回答案作成中"


def test_overdue_response_detected(db_path):
    job_id = _insert_record(db_path)
    with session(db_path) as conn:
        record_id = create_application_history(conn, job_id)
        past_due = (datetime.datetime.now() - datetime.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        create_client_response(conn, {
            "application_record_id": record_id, "received_at": now_jst_str(), "response_type": "質問",
            "response_body": "テスト", "response_due_at": past_due,
        })

    with session(db_path) as conn:
        overdue = get_overdue_responses(conn)
    assert any(r["application_record_id"] == record_id for r in overdue)


def test_not_overdue_response_excluded(db_path):
    job_id = _insert_record(db_path)
    with session(db_path) as conn:
        record_id = create_application_history(conn, job_id)
        future_due = (datetime.datetime.now() + datetime.timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S")
        create_client_response(conn, {
            "application_record_id": record_id, "received_at": now_jst_str(), "response_type": "質問",
            "response_body": "テスト", "response_due_at": future_due,
        })

    with session(db_path) as conn:
        overdue = get_overdue_responses(conn)
    assert all(r["application_record_id"] != record_id for r in overdue)


def test_unhandled_responses_listed(db_path):
    job_id = _insert_record(db_path)
    with session(db_path) as conn:
        record_id = create_application_history(conn, job_id)
        record_response(conn, record_id, "質問", "質問1")
        response_id2 = record_response(conn, record_id, "質問", "質問2")
        update_response_status(conn, response_id2, "対応不要")

    with session(db_path) as conn:
        unhandled = get_unhandled_responses(conn)
    assert len(unhandled) == 1
