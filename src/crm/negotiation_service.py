"""条件相談（金額・納期・修正回数・支払い条件等）の記録。案件ごとに1行を更新し続ける。"""
from __future__ import annotations

import sqlite3

from src.config import AGREEMENT_STATUS_NEGOTIATING, APP_STATUS_NEGOTIATING
from src.crm.application_history_service import change_application_status
from src.crm.timeline_service import add_event
from src.logger import get_logger
from src.repositories import create_negotiation_record, get_negotiation_record, update_negotiation_record

logger = get_logger()


def save_negotiation(conn: sqlite3.Connection, application_record_id: int, data: dict) -> dict:
    """条件相談の内容を保存する（既存があれば更新、無ければ新規作成）。"""
    existing = get_negotiation_record(conn, application_record_id)
    payload = dict(data)
    payload["application_record_id"] = application_record_id

    if existing:
        update_negotiation_record(conn, existing["id"], payload)
        negotiation_id = existing["id"]
    else:
        negotiation_id = create_negotiation_record(conn, payload)

    add_event(
        conn, application_record_id, "条件変更", event_title="条件相談の内容を更新しました",
        event_detail=payload.get("memo"), related_table="negotiation_records", related_id=negotiation_id,
    )

    if payload.get("agreement_status") == AGREEMENT_STATUS_NEGOTIATING:
        change_application_status(conn, application_record_id, APP_STATUS_NEGOTIATING, change_reason="条件相談中")

    logger.info("条件相談を保存しました: application_record_id=%s", application_record_id)
    return get_negotiation_record(conn, application_record_id)


def get_negotiation(conn: sqlite3.Connection, application_record_id: int) -> dict | None:
    return get_negotiation_record(conn, application_record_id)
