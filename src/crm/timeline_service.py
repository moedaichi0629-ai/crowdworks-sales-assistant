"""応募案件タイムライン（応募・ステータス変更・返信・面談・条件変更・結果・フォローアップ）の記録・取得。"""
from __future__ import annotations

import sqlite3

from src.repositories import add_timeline_event, list_timeline as _list_timeline


def add_event(
    conn: sqlite3.Connection,
    application_record_id: int,
    event_type: str,
    event_title: str | None = None,
    event_detail: str | None = None,
    related_table: str | None = None,
    related_id: int | None = None,
    event_at: str | None = None,
) -> int:
    return add_timeline_event(
        conn, application_record_id, event_type, event_title, event_detail,
        related_table, related_id, event_at,
    )


def get_timeline(conn: sqlite3.Connection, application_record_id: int) -> list[dict]:
    return _list_timeline(conn, application_record_id)
