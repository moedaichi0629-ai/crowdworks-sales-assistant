"""応募の記録を扱うサービス層。応募上限の判定・警告を含む。

Part1で導入した「応募済みとして記録する」操作は、Part2では正式な応募履歴
（`src.crm.application_history_service.create_application_history`）としてスナップショット付きで
保存されるようになった。本モジュールは、その前段にある「1日の応募上限チェック」の窓口として残す。
クラウドワークスへの自動応募・自動送信・ブラウザ自動操作は一切行わない
（この記録はユーザーが手動で応募した「事実」を保存するのみ）。
"""
from __future__ import annotations

import sqlite3

from src.applications.application_limit_service import get_limit_status, log_limit_event
from src.config import DEFAULT_SOURCE_PLATFORM
from src.crm.application_history_service import DuplicateApplicationError, create_application_history
from src.logger import get_logger
from src.repositories import list_application_records_for_job

logger = get_logger()


class OverLimitReasonRequiredError(Exception):
    """応募上限を超えて記録しようとしたが、理由が入力されていない場合に送出する。"""


def record_application(
    conn: sqlite3.Connection,
    target_date: str,
    job_id: int,
    application_draft_id: int | None,
    proposed_price: int | None,
    proposed_delivery_days: int | None,
    user_memo: str | None = None,
    over_limit_reason: str | None = None,
    source_platform: str = DEFAULT_SOURCE_PLATFORM,
    contract_type: str | None = None,
    tax_type: str | None = None,
    is_reapplication: bool = False,
    reapplication_reason: str | None = None,
) -> int:
    """応募を正式に記録する。応募上限に達している場合は理由の入力が無いと記録できない。

    同一案件への重複応募は `DuplicateApplicationError` として呼び出し元（画面）へ伝播する。
    """
    status = get_limit_status(conn, target_date)
    is_over_limit = status["limit_reached"]

    if is_over_limit and not (over_limit_reason or "").strip():
        raise OverLimitReasonRequiredError("応募上限を超えて記録するには理由の入力が必要です。")

    record_id = create_application_history(
        conn, job_id, application_draft_id=application_draft_id, target_date=target_date,
        source_platform=source_platform, contract_type=contract_type, tax_type=tax_type,
        proposed_price=proposed_price, proposed_delivery_days=proposed_delivery_days,
        user_memo=user_memo, is_over_limit=is_over_limit, over_limit_reason=over_limit_reason,
        is_reapplication=is_reapplication, reapplication_reason=reapplication_reason,
    )

    new_count = status["applied_count"] + 1
    log_limit_event(target_date, new_count, status["maximum_count"], is_over_limit)
    logger.info("応募を記録しました: job_id=%s target_date=%s 上限超過=%s", job_id, target_date, is_over_limit)
    return record_id


def get_records_for_job(conn: sqlite3.Connection, job_id: int) -> list[dict]:
    return list_application_records_for_job(conn, job_id)


__all__ = ["OverLimitReasonRequiredError", "DuplicateApplicationError", "record_application", "get_records_for_job"]
