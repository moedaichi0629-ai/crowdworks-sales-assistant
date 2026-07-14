"""営業文の編集履歴（バージョン）管理サービス。"""
from __future__ import annotations

import sqlite3

from src.logger import get_logger
from src.repositories import (
    add_application_version,
    get_application_version,
    list_application_versions,
    update_application_draft,
)

logger = get_logger()


def record_version(
    conn: sqlite3.Connection,
    draft_id: int,
    application_message: str,
    short_message: str | None = None,
    version_type: str = "generated",
    change_instruction: str | None = None,
    created_by: str = "system",
) -> int:
    return add_application_version(
        conn, draft_id, application_message, short_message, version_type, change_instruction, created_by,
    )


def get_version_history(conn: sqlite3.Connection, draft_id: int) -> list[dict]:
    return list_application_versions(conn, draft_id)


def revert_to_version(conn: sqlite3.Connection, draft_id: int, version_id: int) -> dict:
    """指定バージョンの内容へ営業文を戻す（元の生成文に戻す機能）。"""
    version = get_application_version(conn, version_id)
    if version is None or version["application_draft_id"] != draft_id:
        raise ValueError("指定されたバージョンが見つかりません。")

    update_application_draft(conn, draft_id, {
        "application_message": version["application_message"],
        "short_message": version.get("short_message"),
        "preparation_status": "修正中",
    })
    record_version(
        conn, draft_id, version["application_message"], version.get("short_message"),
        version_type="revert", change_instruction=f"バージョン{version['version_number']}へ復元",
        created_by="user",
    )
    logger.info("営業文を過去バージョンへ復元しました: draft_id=%s version_id=%s", draft_id, version_id)
    return version
