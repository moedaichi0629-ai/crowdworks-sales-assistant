"""分析結果のキャッシュ（同一内容の再分析でAPIを無駄に呼ばないようにする）。"""
from __future__ import annotations

import hashlib
import sqlite3


def compute_content_hash(
    job: dict,
    profile_updated_at: str | None,
    prompt_version: str,
    provider: str,
    model: str | None,
    profile_version: int | None = None,
) -> str:
    """案件内容・プロフィール更新日時(+バージョン)・プロンプト版・AIプロバイダー/モデルからハッシュ値を作る。

    `profile_version` はプロフィール更新のたびに増加するカウンタ。
    `updated_at` は秒単位の解像度しかなく、短時間に連続更新された場合に
    同一時刻となりキャッシュが誤って再利用される恐れがあるため、
    より確実な変更検知のために version も合わせてハッシュへ含める。
    """
    parts = [
        str(job.get("title") or ""),
        str(job.get("body") or job.get("description") or ""),
        str(job.get("budget_text") or ""),
        str(job.get("deadline") or ""),
        str(profile_updated_at or ""),
        str(profile_version if profile_version is not None else ""),
        str(prompt_version or ""),
        str(provider or ""),
        str(model or ""),
    ]
    joined = "\x1f".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def get_cached_analysis(conn: sqlite3.Connection, job_id: int, content_hash: str) -> dict | None:
    """同一ハッシュの分析結果が既に存在すれば返す。なければNone。"""
    row = conn.execute(
        """
        SELECT * FROM job_analyses
        WHERE job_id = ? AND content_hash = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (job_id, content_hash),
    ).fetchone()
    return dict(row) if row else None
