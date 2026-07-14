"""案件一覧のCSV / Excel書き出し機能。"""
from __future__ import annotations

import io

import pandas as pd

EXPORT_COLUMNS = [
    "id", "title", "url", "job_type", "category", "budget_text", "budget_min",
    "budget_max", "published_at", "deadline", "applicant_count", "recruitment_count",
    "client_name", "client_rating", "identity_verified", "matched_keyword", "status",
    "is_favorite", "memo", "collected_at",
]

EXPORT_COLUMN_LABELS_JA = {
    "id": "内部ID",
    "title": "案件タイトル",
    "url": "案件URL",
    "job_type": "募集形式",
    "category": "カテゴリ",
    "budget_text": "予算",
    "budget_min": "予算下限",
    "budget_max": "予算上限",
    "published_at": "掲載日時",
    "deadline": "応募期限",
    "applicant_count": "応募人数",
    "recruitment_count": "採用人数",
    "client_name": "クライアント名",
    "client_rating": "クライアント評価",
    "identity_verified": "本人確認",
    "matched_keyword": "検索キーワード",
    "status": "ステータス",
    "is_favorite": "お気に入り",
    "memo": "メモ",
    "collected_at": "取得日時",
}


def _prepare_export_df(df: pd.DataFrame) -> pd.DataFrame:
    columns = [c for c in EXPORT_COLUMNS if c in df.columns]
    export_df = df[columns].copy()
    return export_df.rename(columns=EXPORT_COLUMN_LABELS_JA)


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    """Excelで文字化けしないよう UTF-8 (BOM付き) のCSVバイト列を生成する。"""
    export_df = _prepare_export_df(df)
    return export_df.to_csv(index=False).encode("utf-8-sig")


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    """Excel(.xlsx)形式のバイト列を生成する。"""
    export_df = _prepare_export_df(df)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="案件一覧")
    return buffer.getvalue()
