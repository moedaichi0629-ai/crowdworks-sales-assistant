"""クライアント返信の記録・回答対応管理。

返信本文には個人情報が含まれる可能性があるため、外部AI（分析・営業文生成API）へは
自動送信しない（要件6・16）。あくまでユーザーが読む・記録するための機能である。
"""
from __future__ import annotations

import datetime
import sqlite3

from src.config import (
    APP_STATUS_APPLIED,
    APP_STATUS_REPLIED,
    APP_STATUS_UNREAD,
    APP_STATUS_VIEWED,
    DEFAULT_RESPONSE_TARGET_HOURS,
    RESPONSE_STATUS_DRAFTING,
    RESPONSE_STATUS_REPLIED,
    RESPONSE_STATUS_UNHANDLED,
)
from src.crm.application_history_service import change_application_status
from src.crm.timeline_service import add_event
from src.logger import get_logger
from src.repositories import (
    create_client_response,
    get_application_record,
    get_client_response,
    list_client_responses,
    list_client_responses_by_status,
    update_client_response,
)
from src.utils import now_jst, now_jst_str

logger = get_logger()

_EARLY_STATUSES = {APP_STATUS_APPLIED, APP_STATUS_UNREAD, APP_STATUS_VIEWED}


def record_response(
    conn: sqlite3.Connection,
    application_record_id: int,
    response_type: str,
    response_body: str,
    response_summary: str | None = None,
    questions: list[str] | None = None,
    urgency: str | None = None,
    target_hours: int = DEFAULT_RESPONSE_TARGET_HOURS,
    next_action: str | None = None,
    memo: str | None = None,
) -> int:
    """クライアントからの返信を記録する。回答期限は受信時刻+目標時間から自動算出する。"""
    received_at = now_jst_str()
    due = now_jst().replace(tzinfo=None) + datetime.timedelta(hours=target_hours)
    response_id = create_client_response(conn, {
        "application_record_id": application_record_id, "received_at": received_at,
        "response_type": response_type, "response_body": response_body, "response_summary": response_summary,
        "questions": questions or [], "response_due_at": due.strftime("%Y-%m-%d %H:%M:%S"),
        "urgency": urgency, "next_action": next_action, "memo": memo,
    })
    add_event(
        conn, application_record_id, "返信受信", event_title=f"返信を受信しました（{response_type}）",
        related_table="client_responses", related_id=response_id,
    )

    record = get_application_record(conn, application_record_id)
    if record and record.get("application_status") in _EARLY_STATUSES:
        change_application_status(conn, application_record_id, APP_STATUS_REPLIED, change_reason="クライアントからの返信を受信")

    logger.info("クライアント返信を記録しました: application_record_id=%s response_type=%s", application_record_id, response_type)
    return response_id


def answer_response(conn: sqlite3.Connection, response_id: int, answer_body: str) -> None:
    """クライアントへの回答内容を記録する（実際の送信操作はユーザーが手動で行う）。"""
    response = get_client_response(conn, response_id)
    if response is None:
        raise ValueError(f"返信が見つかりません: response_id={response_id}")
    update_client_response(conn, response_id, {
        "answer_body": answer_body, "answered_at": now_jst_str(), "response_status": RESPONSE_STATUS_REPLIED,
    })
    add_event(
        conn, response["application_record_id"], "返信送信", event_title="クライアントへ回答しました",
        related_table="client_responses", related_id=response_id,
    )
    logger.info("返信への回答を記録しました: response_id=%s", response_id)


def update_response_status(conn: sqlite3.Connection, response_id: int, status: str) -> None:
    update_client_response(conn, response_id, {"response_status": status})
    logger.info("返信対応状況を変更しました: response_id=%s status=%s", response_id, status)


def get_unhandled_responses(conn: sqlite3.Connection) -> list[dict]:
    return list_client_responses_by_status(conn, [RESPONSE_STATUS_UNHANDLED, RESPONSE_STATUS_DRAFTING])


def get_overdue_responses(conn: sqlite3.Connection) -> list[dict]:
    """回答期限を過ぎている、未対応の返信を返す。"""
    now = now_jst_str()
    return [r for r in get_unhandled_responses(conn) if r.get("response_due_at") and r["response_due_at"] < now]


def get_responses_for_record(conn: sqlite3.Connection, application_record_id: int) -> list[dict]:
    return list_client_responses(conn, application_record_id)
