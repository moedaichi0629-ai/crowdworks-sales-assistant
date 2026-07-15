"""フォローアップ管理(follow_up_service)のテスト。"""
from __future__ import annotations

import datetime

from src.crm.application_history_service import create_application_history
from src.crm.follow_up_service import (
    complete_task,
    create_task,
    get_completed_tasks,
    get_overdue_tasks,
    get_tasks_for_record,
    get_today_tasks,
    get_upcoming_tasks,
)
from src.database import session
from src.repositories import insert_job
from src.utils import now_jst_str


def _insert_record(db_path) -> int:
    with session(db_path) as conn:
        job_id = insert_job(conn, {"title": "フォローアップテスト案件", "source_type": "manual"})
        return create_application_history(conn, job_id)


def test_create_task(db_path):
    record_id = _insert_record(db_path)
    with session(db_path) as conn:
        task_id = create_task(conn, record_id, due_at="2026-08-01 10:00:00", task_type="返信確認", task_content="返信の有無を確認する")

    with session(db_path) as conn:
        tasks = get_tasks_for_record(conn, record_id)
    assert len(tasks) == 1
    assert tasks[0]["id"] == task_id
    assert tasks[0]["status"] == "未対応"


def test_overdue_task_detected(db_path):
    record_id = _insert_record(db_path)
    past = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    with session(db_path) as conn:
        create_task(conn, record_id, due_at=past, task_type="返信確認")

    with session(db_path) as conn:
        overdue = get_overdue_tasks(conn)
    assert any(t["application_record_id"] == record_id for t in overdue)


def test_completed_task_excluded_from_overdue(db_path):
    record_id = _insert_record(db_path)
    past = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    with session(db_path) as conn:
        task_id = create_task(conn, record_id, due_at=past, task_type="返信確認")
        complete_task(conn, task_id)

    with session(db_path) as conn:
        overdue = get_overdue_tasks(conn)
        completed = get_completed_tasks(conn)
    assert all(t["id"] != task_id for t in overdue)
    assert any(t["id"] == task_id for t in completed)


def test_today_task_filter(db_path):
    record_id = _insert_record(db_path)
    today_due = now_jst_str()[:10] + " 09:00:00"
    future_due = (datetime.datetime.now() + datetime.timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
    with session(db_path) as conn:
        create_task(conn, record_id, due_at=today_due, task_type="返信確認")
        create_task(conn, record_id, due_at=future_due, task_type="納期確認")

    with session(db_path) as conn:
        today_tasks = get_today_tasks(conn)
    assert len(today_tasks) == 1
    assert today_tasks[0]["due_at"] == today_due


def test_upcoming_task_filter_within_7_days(db_path):
    record_id = _insert_record(db_path)
    within = (datetime.datetime.now() + datetime.timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
    beyond = (datetime.datetime.now() + datetime.timedelta(days=20)).strftime("%Y-%m-%d %H:%M:%S")
    with session(db_path) as conn:
        create_task(conn, record_id, due_at=within, task_type="面談準備")
        create_task(conn, record_id, due_at=beyond, task_type="面談準備")

    with session(db_path) as conn:
        upcoming = get_upcoming_tasks(conn, days=7)
    assert len(upcoming) == 1
    assert upcoming[0]["due_at"] == within
