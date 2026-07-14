"""CSVアップロードによる案件の一括登録機能。"""
from __future__ import annotations

import io
import sqlite3
from typing import Optional

import pandas as pd

from src.config import SOURCE_TYPE_CSV
from src.logger import get_logger
from src.parsers import parse_budget, parse_date
from src.repositories import log_import, upsert_job
from src.utils import now_jst_str
from src.validators import ValidationError, validate_csv_extension, validate_csv_file_size

logger = get_logger()

# 内部フィールド名 -> 対応するCSV列名候補（英語・日本語）
COLUMN_ALIASES: dict[str, list[str]] = {
    "external_job_id": ["external_job_id", "外部案件ID"],
    "title": ["title", "案件タイトル", "タイトル"],
    "url": ["url", "案件URL", "URL"],
    "description": ["description", "案件概要", "概要"],
    "body": ["body", "案件本文", "本文"],
    "job_type": ["job_type", "募集形式"],
    "category": ["category", "カテゴリ"],
    "budget": ["budget", "予算"],
    "budget_min": ["budget_min", "予算下限"],
    "budget_max": ["budget_max", "予算上限"],
    "published_at": ["published_at", "掲載日時", "掲載日"],
    "deadline": ["deadline", "応募期限"],
    "applicant_count": ["applicant_count", "応募人数"],
    "recruitment_count": ["recruitment_count", "採用人数"],
    "client_name": ["client_name", "クライアント名"],
    "client_rating": ["client_rating", "クライアント評価"],
    "identity_verified": ["identity_verified", "本人確認", "本人確認の有無"],
    "keyword": ["keyword", "検索キーワード"],
    "memo": ["memo", "メモ"],
}

REQUIRED_INTERNAL_FIELD = "title"


def read_csv_bytes(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """アップロードされたCSVバイト列を検証し、DataFrameとして読み込む。

    文字コードはUTF-8(BOM付き) -> CP932 の順に試す。
    """
    validate_csv_extension(filename)
    validate_csv_file_size(len(file_bytes))

    last_error: Optional[Exception] = None
    for encoding in ("utf-8-sig", "cp932", "shift_jis"):
        try:
            return pd.read_csv(io.BytesIO(file_bytes), encoding=encoding, dtype=str)
        except (UnicodeDecodeError, pd.errors.ParserError) as exc:
            last_error = exc
            continue

    raise ValidationError(
        "CSVの文字コードを判定できませんでした。UTF-8またはShift-JIS(CP932)で保存し直してください。"
    ) from last_error


def auto_map_columns(csv_columns: list[str]) -> tuple[dict[str, str], list[str]]:
    """CSV列名を内部フィールド名へ自動マッピングする。

    戻り値は (内部フィールド名 -> CSV列名 の辞書, マッピングできなかった内部フィールド一覧)。
    """
    mapping: dict[str, str] = {}
    normalized_columns = {c.strip(): c for c in csv_columns}

    for field, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalized_columns:
                mapping[field] = normalized_columns[alias]
                break

    unmapped = [f for f in COLUMN_ALIASES if f not in mapping]
    return mapping, unmapped


def _row_to_job_dict(row: pd.Series, mapping: dict[str, str], default_keyword: str = "") -> dict:
    def get(field: str) -> Optional[str]:
        col = mapping.get(field)
        if col is None or col not in row:
            return None
        value = row[col]
        if pd.isna(value):
            return None
        value = str(value).strip()
        return value or None

    data: dict = {
        "external_job_id": get("external_job_id"),
        "title": get("title"),
        "url": get("url"),
        "description": get("description"),
        "body": get("body"),
        "job_type": get("job_type"),
        "category": get("category"),
        "published_at": parse_date(get("published_at")),
        "deadline": parse_date(get("deadline")),
        "client_name": get("client_name"),
        "memo": get("memo"),
        "source_type": SOURCE_TYPE_CSV,
        "collected_at": now_jst_str(),
    }

    applicant_count = get("applicant_count")
    data["applicant_count"] = int(applicant_count) if applicant_count and applicant_count.isdigit() else None

    recruitment_count = get("recruitment_count")
    data["recruitment_count"] = int(recruitment_count) if recruitment_count and recruitment_count.isdigit() else None

    client_rating = get("client_rating")
    try:
        data["client_rating"] = float(client_rating) if client_rating else None
    except ValueError:
        data["client_rating"] = None

    identity_verified = get("identity_verified")
    if identity_verified is not None:
        data["identity_verified"] = 1 if identity_verified.strip() in ("1", "true", "True", "有", "あり") else 0
    else:
        data["identity_verified"] = None

    budget_min = get("budget_min")
    budget_max = get("budget_max")
    if budget_min or budget_max:
        data["budget_min"] = int(budget_min) if budget_min and budget_min.isdigit() else None
        data["budget_max"] = int(budget_max) if budget_max and budget_max.isdigit() else None
        data["budget_text"] = get("budget")
    else:
        bmin, bmax, btext = parse_budget(get("budget"))
        data["budget_min"], data["budget_max"], data["budget_text"] = bmin, bmax, btext

    keyword = get("keyword") or default_keyword
    data["matched_keyword"] = keyword or None

    return {k: v for k, v in data.items() if v is not None}


def import_dataframe(
    conn: sqlite3.Connection,
    df: pd.DataFrame,
    mapping: dict[str, str],
    source_name: str,
    default_keyword: str = "",
) -> dict:
    """DataFrameを案件として一括登録する。結果サマリーを返す。"""
    inserted = updated = duplicate = errors = 0
    error_rows: list[dict] = []

    logger.info("CSVインポートを開始します: source=%s rows=%s", source_name, len(df))

    for idx, row in df.iterrows():
        try:
            data = _row_to_job_dict(row, mapping, default_keyword)
            if not data.get("title"):
                raise ValidationError("案件タイトルが空です。")
            action, _job_id = upsert_job(conn, data)
            if action == "inserted":
                inserted += 1
            elif action == "updated":
                updated += 1
            else:
                duplicate += 1
        except Exception as exc:  # noqa: BLE001 - 行単位でエラーを収集し処理継続する
            errors += 1
            reason = str(exc)
            error_rows.append({"row": idx + 2, "reason": reason})
            logger.warning("CSVインポート行エラー: row=%s reason=%s", idx + 2, reason)

    total = len(df)
    log_import(
        conn,
        source_type=SOURCE_TYPE_CSV,
        source_name=source_name,
        total_count=total,
        inserted_count=inserted,
        updated_count=updated,
        duplicate_count=duplicate,
        error_count=errors,
        error_detail="; ".join(f"{r['row']}行目: {r['reason']}" for r in error_rows),
    )
    logger.info(
        "CSVインポートが完了しました: total=%s inserted=%s updated=%s duplicate=%s error=%s",
        total, inserted, updated, duplicate, errors,
    )

    return {
        "total": total,
        "inserted": inserted,
        "updated": updated,
        "duplicate": duplicate,
        "errors": errors,
        "error_rows": error_rows,
    }
