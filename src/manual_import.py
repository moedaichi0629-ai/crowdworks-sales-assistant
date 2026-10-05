"""手動入力による案件登録機能。"""
from __future__ import annotations

import sqlite3
from urllib.parse import urlsplit

from src.config import SOURCE_TYPE_MANUAL
from src.duplicate_checker import find_duplicate
from src.parsers import extract_fields_from_body, parse_budget, parse_date
from src.repositories import insert_job, upsert_job
from src.utils import normalize_url, now_jst_str
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


def build_job_from_url_only(url: str) -> dict:
    """URLのみ判明している案件を、後から編集する前提の下書きとして登録するためのデータを組み立てる。

    自動取得が禁止されたドメイン（crowdworks.jp 等）のURLを一括で下書き登録し、
    タイトル・本文は案件一覧から手動で編集してもらう運用を想定している。
    """
    validated = validate_url_format(url)
    if not validated:
        raise ValidationError("URLを入力してください。")

    path = urlsplit(validated).path.rstrip("/")
    hint = path.rsplit("/", 1)[-1] if path else validated
    return {
        "title": f"（タイトル未入力）{hint}",
        "url": validated,
        "source_type": SOURCE_TYPE_MANUAL,
        "collected_at": now_jst_str(),
        "memo": "URLのみ一括登録した下書きです。案件一覧からタイトル・本文を編集してください。",
    }


def save_url_only_jobs(conn: sqlite3.Connection, urls: list[str]) -> dict:
    """URLのみで複数案件を下書き登録する。

    既存案件と同じURLの場合は上書きせず「重複」として扱う
    （タイトル未入力のプレースホルダーで既存データを壊さないため）。
    戻り値: {"total", "inserted", "duplicate", "errors", "error_rows"}
    """
    targets = [u.strip() for u in urls if u.strip()]
    inserted = duplicate = errors = 0
    error_rows: list[dict] = []

    for url in targets:
        try:
            data = build_job_from_url_only(url)
        except ValidationError as exc:
            errors += 1
            error_rows.append({"url": url, "reason": str(exc)})
            continue

        existing = find_duplicate(conn, {"normalized_url": normalize_url(data["url"])})
        if existing is not None:
            duplicate += 1
            continue

        insert_job(conn, data)
        inserted += 1

    return {
        "total": len(targets), "inserted": inserted, "duplicate": duplicate,
        "errors": errors, "error_rows": error_rows,
    }
