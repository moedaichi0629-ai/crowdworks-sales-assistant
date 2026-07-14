"""応募前確認チェックリストのサービス層。"""
from __future__ import annotations

import sqlite3

from src.config import PREP_STATUS_READY
from src.logger import get_logger
from src.repositories import get_application_checklist, save_application_checklist, update_application_draft

logger = get_logger()

CHECKLIST_LABELS: dict[str, str] = {
    "job_reviewed": "案件内容を確認した",
    "conditions_confirmed": "応募条件を満たしている",
    "price_confirmed": "応募金額を確認した",
    "deadline_confirmed": "納期を確認した",
    "message_confirmed": "営業文を確認した",
    "portfolio_confirmed": "選択されたポートフォリオ・URLが案件に適していることを確認した",
    "client_questions_answered": "クライアントの質問に回答した",
    "safety_confirmed": "危険事項がないことを確認した",
}


def get_checklist(conn: sqlite3.Connection, draft_id: int) -> dict:
    checklist = get_application_checklist(conn, draft_id)
    if checklist is None:
        return {field: False for field in CHECKLIST_LABELS}
    return {field: checklist.get(field, False) for field in CHECKLIST_LABELS}


def save_checklist(conn: sqlite3.Connection, draft_id: int, values: dict) -> bool:
    """チェックリストを保存する。全項目チェック済みなら応募準備ステータスを「応募準備完了」にする。"""
    save_application_checklist(conn, draft_id, values)
    all_checked = all(values.get(field, False) for field in CHECKLIST_LABELS)
    if all_checked:
        update_application_draft(conn, draft_id, {"preparation_status": PREP_STATUS_READY})
        logger.info("応募前確認が完了し、応募準備完了に変更しました: draft_id=%s", draft_id)
    return all_checked
