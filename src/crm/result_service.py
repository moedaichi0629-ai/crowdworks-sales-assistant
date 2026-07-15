"""採用・不採用・辞退の結果記録。"""
from __future__ import annotations

import sqlite3

from src.config import (
    APP_STATUS_HIRED,
    APP_STATUS_REJECTED,
    APP_STATUS_WITHDRAWN,
    RESULT_TYPE_HIRED,
    RESULT_TYPE_REJECTED,
    RESULT_TYPE_WITHDRAWN,
)
from src.crm.application_history_service import change_application_status
from src.crm.timeline_service import add_event
from src.logger import get_logger
from src.repositories import create_application_result, get_latest_application_result
from src.utils import now_jst_str

logger = get_logger()


def record_hired(
    conn: sqlite3.Connection,
    application_record_id: int,
    hired_at: str | None = None,
    contracted_at: str | None = None,
    contract_amount: int | None = None,
    contract_type: str | None = None,
    contract_start_date: str | None = None,
    contract_end_date: str | None = None,
    planned_delivery_date: str | None = None,
    client_comment: str | None = None,
    continuation_possible: str | None = None,
    is_recurring: bool = False,
    memo: str | None = None,
) -> int:
    hired_at = hired_at or now_jst_str()[:10]
    result_id = create_application_result(conn, {
        "application_record_id": application_record_id, "result_type": RESULT_TYPE_HIRED,
        "result_date": hired_at, "hired_at": hired_at, "contracted_at": contracted_at,
        "contract_amount": contract_amount, "contract_type": contract_type,
        "contract_start_date": contract_start_date, "contract_end_date": contract_end_date,
        "planned_delivery_date": planned_delivery_date, "client_comment": client_comment,
        "continuation_possible": continuation_possible, "is_recurring": is_recurring, "memo": memo,
    })
    add_event(
        conn, application_record_id, "採用", event_title="採用が決まりました",
        related_table="application_results", related_id=result_id,
    )
    change_application_status(conn, application_record_id, APP_STATUS_HIRED, change_reason="採用決定")
    logger.info("採用を記録しました: application_record_id=%s", application_record_id)
    return result_id


def record_rejected(
    conn: sqlite3.Connection,
    application_record_id: int,
    client_reason: str | None = None,
    inferred_reason: str | None = None,
    client_comment: str | None = None,
    improvement_points: list[str] | None = None,
    memo: str | None = None,
) -> int:
    result_id = create_application_result(conn, {
        "application_record_id": application_record_id, "result_type": RESULT_TYPE_REJECTED,
        "result_date": now_jst_str()[:10], "client_reason": client_reason, "inferred_reason": inferred_reason,
        "client_comment": client_comment, "improvement_points": improvement_points or [], "memo": memo,
    })
    add_event(
        conn, application_record_id, "不採用", event_title="不採用となりました", event_detail=client_reason,
        related_table="application_results", related_id=result_id,
    )
    change_application_status(conn, application_record_id, APP_STATUS_REJECTED, change_reason="不採用")
    logger.info("不採用を記録しました: application_record_id=%s reason=%s", application_record_id, client_reason)
    return result_id


def record_withdrawn(
    conn: sqlite3.Connection, application_record_id: int, withdrawal_reason: str | None = None, memo: str | None = None,
) -> int:
    result_id = create_application_result(conn, {
        "application_record_id": application_record_id, "result_type": RESULT_TYPE_WITHDRAWN,
        "result_date": now_jst_str()[:10], "withdrawal_reason": withdrawal_reason, "memo": memo,
    })
    add_event(
        conn, application_record_id, "辞退", event_title="辞退しました", event_detail=withdrawal_reason,
        related_table="application_results", related_id=result_id,
    )
    change_application_status(conn, application_record_id, APP_STATUS_WITHDRAWN, change_reason="辞退")
    logger.info("辞退を記録しました: application_record_id=%s", application_record_id)
    return result_id


def get_result(conn: sqlite3.Connection, application_record_id: int) -> dict | None:
    return get_latest_application_result(conn, application_record_id)
