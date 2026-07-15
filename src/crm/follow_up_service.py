"""フォローアップ（応募後、結果が出ていない案件への確認・整理タスク）管理。自動送信は行わない。"""
from __future__ import annotations

import datetime
import sqlite3

from src.config import FOLLOW_UP_STATUS_DONE
from src.crm.timeline_service import add_event
from src.logger import get_logger
from src.repositories import (
    create_follow_up_task,
    get_follow_up_task,
    list_all_follow_up_tasks,
    list_follow_up_tasks,
    update_follow_up_task,
)
from src.utils import now_jst, now_jst_str

logger = get_logger()


def create_task(
    conn: sqlite3.Connection, application_record_id: int, due_at: str, task_type: str,
    task_content: str | None = None, memo: str | None = None,
) -> int:
    task_id = create_follow_up_task(conn, {
        "application_record_id": application_record_id, "due_at": due_at, "task_type": task_type,
        "task_content": task_content, "memo": memo,
    })
    add_event(
        conn, application_record_id, "フォローアップ", event_title=f"フォローアップを設定しました（{task_type}）",
        event_at=due_at, related_table="follow_up_tasks", related_id=task_id,
    )
    logger.info("フォローアップを作成しました: application_record_id=%s task_type=%s", application_record_id, task_type)
    return task_id


def complete_task(conn: sqlite3.Connection, task_id: int) -> None:
    task = get_follow_up_task(conn, task_id)
    update_follow_up_task(conn, task_id, {"status": FOLLOW_UP_STATUS_DONE, "completed_at": now_jst_str()})
    if task:
        add_event(
            conn, task["application_record_id"], "フォローアップ", event_title="フォローアップが完了しました",
            related_table="follow_up_tasks", related_id=task_id,
        )
    logger.info("フォローアップを完了しました: task_id=%s", task_id)


def update_task_status(conn: sqlite3.Connection, task_id: int, status: str) -> None:
    update_follow_up_task(conn, task_id, {"status": status})
    logger.info("フォローアップの対応状況を変更しました: task_id=%s status=%s", task_id, status)


def get_tasks_for_record(conn: sqlite3.Connection, application_record_id: int) -> list[dict]:
    return list_follow_up_tasks(conn, application_record_id)


def get_all_tasks(conn: sqlite3.Connection) -> list[dict]:
    return list_all_follow_up_tasks(conn)


def get_overdue_tasks(conn: sqlite3.Connection) -> list[dict]:
    now = now_jst_str()
    return [t for t in get_all_tasks(conn) if t.get("status") != FOLLOW_UP_STATUS_DONE and t.get("due_at") and t["due_at"] < now]


def get_today_tasks(conn: sqlite3.Connection) -> list[dict]:
    today = now_jst_str()[:10]
    return [
        t for t in get_all_tasks(conn)
        if t.get("status") != FOLLOW_UP_STATUS_DONE and (t.get("due_at") or "")[:10] == today
    ]


def get_upcoming_tasks(conn: sqlite3.Connection, days: int = 7) -> list[dict]:
    now = now_jst().replace(tzinfo=None)
    until = now + datetime.timedelta(days=days)
    now_str, until_str = now.strftime("%Y-%m-%d %H:%M:%S"), until.strftime("%Y-%m-%d %H:%M:%S")
    return [
        t for t in get_all_tasks(conn)
        if t.get("status") != FOLLOW_UP_STATUS_DONE and t.get("due_at") and now_str <= t["due_at"] <= until_str
    ]


def get_completed_tasks(conn: sqlite3.Connection) -> list[dict]:
    return [t for t in get_all_tasks(conn) if t.get("status") == FOLLOW_UP_STATUS_DONE]
