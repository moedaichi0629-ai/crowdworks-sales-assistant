"""案件の重複判定ロジック。

優先順位:
1. 外部案件ID (external_job_id)
2. 正規化した案件URL (normalized_url)
3. 案件タイトル + クライアント名
4. 案件タイトル + 案件本文の類似度
"""
from __future__ import annotations

import sqlite3
from difflib import SequenceMatcher
from typing import Optional

SIMILARITY_THRESHOLD = 0.9


def _text_similarity(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def find_duplicate(conn: sqlite3.Connection, candidate: dict) -> Optional[sqlite3.Row]:
    """既存案件の中から重複と判定できる行を1件返す。なければNone。"""

    external_job_id = candidate.get("external_job_id")
    if external_job_id:
        row = conn.execute(
            "SELECT * FROM jobs WHERE external_job_id = ? LIMIT 1", (external_job_id,)
        ).fetchone()
        if row:
            return row

    normalized_url = candidate.get("normalized_url")
    if normalized_url:
        row = conn.execute(
            "SELECT * FROM jobs WHERE normalized_url = ? LIMIT 1", (normalized_url,)
        ).fetchone()
        if row:
            return row

    title = candidate.get("title")
    client_name = candidate.get("client_name")
    if title and client_name:
        row = conn.execute(
            "SELECT * FROM jobs WHERE title = ? AND client_name = ? LIMIT 1",
            (title, client_name),
        ).fetchone()
        if row:
            return row

    if title:
        body = candidate.get("body")
        rows = conn.execute(
            "SELECT * FROM jobs WHERE title = ?", (title,)
        ).fetchall()
        for row in rows:
            if _text_similarity(body, row["body"]) >= SIMILARITY_THRESHOLD:
                return row

    return None
