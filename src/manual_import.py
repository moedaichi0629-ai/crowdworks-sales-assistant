"""手動入力による案件登録機能。"""
from __future__ import annotations

import sqlite3

from src.config import SOURCE_TYPE_MANUAL
from src.parsers import extract_fields_from_body, parse_budget, parse_date
from src.repositories import upsert_job
from src.utils import now_jst_str
from src.validators import ValidationError, validate_required_title, validate_url_format


def extract_preview_from_body(body: str | None) -> dict:
    """案件本文から予算・応募期限などを補助的に抽出する（保存前プレビュー用）。"""
    return extract_fields_from_body(body)


def build_job_from_manual_input(form_data: dict) -> dict:
    """手動入力フォームの内容から案件データ辞書を組み立てる。

    必須項目は案件タイトルのみ。それ以外は空欄でも保存できる。
    """
    title = validate_required_title(form_data.get("title"))
    url = validate_url_format(form_data.get("url"))

    budget_min = form_data.get("budget_min")
    budget_max = form_data.get("budget_max")
    budget_text = form_data.get("budget_text")
    if not budget_min and not budget_max and budget_text:
        budget_min, budget_max, budget_text = parse_budget(budget_text)

    data = {
        "title": title,
        "url": url,
        "body": form_data.get("body") or None,
        "description": form_data.get("description") or None,
        "job_type": form_data.get("job_type") or None,
        "category": form_data.get("category") or None,
        "budget_min": budget_min or None,
        "budget_max": budget_max or None,
        "budget_text": budget_text or None,
        "published_at": parse_date(form_data.get("published_at")) or form_data.get("published_at") or None,
        "deadline": parse_date(form_data.get("deadline")) or form_data.get("deadline") or None,
        "applicant_count": form_data.get("applicant_count") or None,
        "recruitment_count": form_data.get("recruitment_count") or None,
        "client_name": form_data.get("client_name") or None,
        "client_rating": form_data.get("client_rating") or None,
        "identity_verified": form_data.get("identity_verified"),
        "matched_keyword": form_data.get("matched_keyword") or None,
        "memo": form_data.get("memo") or None,
        "source_type": SOURCE_TYPE_MANUAL,
        "collected_at": now_jst_str(),
    }
    return {k: v for k, v in data.items() if v is not None}


def save_manual_job(conn: sqlite3.Connection, form_data: dict) -> tuple[str, int]:
    """手動入力内容をバリデーションして保存する。戻り値は (inserted|updated|duplicate, job_id)。"""
    data = build_job_from_manual_input(form_data)
    return upsert_job(conn, data)
