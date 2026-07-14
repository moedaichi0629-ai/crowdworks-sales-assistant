"""営業文生成結果のキャッシュ（同一条件での再生成でAPIを無駄に呼ばないようにする）。

案件内容・AI分析結果・プロフィール・選択ポートフォリオ・生成条件（タイプ/トーン/長さ/金額/納期/
追加指示/プロンプト版/プロバイダー/モデル）からハッシュ値を作る。
手動編集した文章は同一hashの下書き行自体に保持されるため、
force_regenerate=False の再生成では上書きされない。
"""
from __future__ import annotations

import hashlib
import sqlite3


def compute_content_hash(
    job: dict,
    analysis_summary: dict | None,
    profile_updated_at: str | None,
    profile_version: int | None,
    selected_portfolio_ids: list[int],
    generation_type: str,
    tone: str,
    length_type: str,
    proposed_price: int | None,
    proposed_delivery_days: int | None,
    additional_message: str | None,
    exclude_content: str | None,
    prompt_version: str,
    provider: str,
    model: str | None,
) -> str:
    parts = [
        str(job.get("title") or ""),
        str(job.get("body") or job.get("description") or ""),
        str(job.get("budget_text") or ""),
        str(job.get("deadline") or ""),
        str((analysis_summary or {}).get("total_score", "")),
        str((analysis_summary or {}).get("application_priority", "")),
        str(profile_updated_at or ""),
        str(profile_version if profile_version is not None else ""),
        ",".join(str(i) for i in sorted(selected_portfolio_ids or [])),
        str(generation_type or ""),
        str(tone or ""),
        str(length_type or ""),
        str(proposed_price if proposed_price is not None else ""),
        str(proposed_delivery_days if proposed_delivery_days is not None else ""),
        str(additional_message or ""),
        str(exclude_content or ""),
        str(prompt_version or ""),
        str(provider or ""),
        str(model or ""),
    ]
    joined = "\x1f".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def get_cached_draft(conn: sqlite3.Connection, job_id: int, source_hash: str) -> dict | None:
    from src.repositories import _application_draft_row_to_dict

    row = conn.execute(
        """
        SELECT * FROM application_drafts
        WHERE job_id = ? AND source_hash = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (job_id, source_hash),
    ).fetchone()
    return _application_draft_row_to_dict(row)
