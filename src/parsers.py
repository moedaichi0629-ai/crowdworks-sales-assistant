"""案件本文・文字列から予算や日付などを抽出するパーサー群。

すべての関数は「解析できない場合は例外を出さずNoneを返す」方針とする。
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from dateutil import parser as dateutil_parser

from src.config import JOB_TYPES

_NUMBER_RE = re.compile(r"[0-9][0-9,，]*")


def _to_int(text: str) -> Optional[int]:
    text = text.replace(",", "").replace("，", "")
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def parse_budget(text: str | None) -> tuple[Optional[int], Optional[int], Optional[str]]:
    """予算文字列から (下限, 上限, 元文字列) を抽出する。

    例: "3万円〜5万円" -> (30000, 50000, "3万円〜5万円")
        "50,000円"     -> (50000, 50000, "50,000円")
        "時給1,500円"   -> (1500, 1500, "時給1,500円")
    """
    if not text:
        return None, None, None
    original = text.strip()
    if not original:
        return None, None, None

    def unit_to_yen(num: float, unit: str) -> int:
        if unit == "万":
            return int(num * 10_000)
        return int(num)

    pattern = re.compile(r"(\d+(?:[.,]\d+)?)\s*(万)?\s*円?")
    matches = []
    for m in pattern.finditer(original):
        num_str = m.group(1).replace(",", "")
        try:
            num = float(num_str)
        except ValueError:
            continue
        matches.append(unit_to_yen(num, m.group(2) or ""))

    if not matches:
        return None, None, original

    if len(matches) == 1:
        return matches[0], matches[0], original

    return min(matches), max(matches), original


def parse_date(text: str | None) -> Optional[str]:
    """日付文字列をYYYY-MM-DD形式へ正規化する。解析できない場合はNone。"""
    if not text:
        return None
    text = text.strip()
    if not text:
        return None

    # "2026年7月20日" のような和暦区切りを扱いやすい形へ変換
    normalized = text.replace("年", "-").replace("月", "-").replace("日", "")
    normalized = re.sub(r"[〜~].*$", "", normalized).strip()

    try:
        dt = dateutil_parser.parse(normalized, fuzzy=True, default=datetime(1900, 1, 1))
    except (ValueError, OverflowError):
        return None

    if dt.year == 1900:
        return None

    return dt.strftime("%Y-%m-%d")


def extract_job_type(text: str | None) -> Optional[str]:
    """本文中から募集形式を推定する。"""
    if not text:
        return None
    for job_type in JOB_TYPES:
        if job_type in text:
            return job_type
    if "時給" in text or "時間単価" in text:
        return "時間単価制"
    if "固定" in text:
        return "固定報酬制"
    return None


def extract_count(text: str | None, label_patterns: list[str]) -> Optional[int]:
    """「応募人数」「採用人数」などのラベル直後の数値を抽出する。"""
    if not text:
        return None
    for label in label_patterns:
        m = re.search(rf"{label}[^0-9]{{0,5}}([0-9]+)", text)
        if m:
            return _to_int(m.group(1))
    return None


def extract_applicant_count(text: str | None) -> Optional[int]:
    return extract_count(text, ["応募人数", "応募者数", "契約数"])


def extract_recruitment_count(text: str | None) -> Optional[int]:
    return extract_count(text, ["採用人数", "募集人数"])


def extract_deadline(text: str | None) -> Optional[str]:
    """本文中の「応募期限」「納期」などから日付を抽出する。"""
    if not text:
        return None
    m = re.search(r"(応募期限|募集期限|締切)[^\n]{0,20}?([0-9]{4}[年/\-][0-9]{1,2}[月/\-][0-9]{1,2}日?)", text)
    if m:
        return parse_date(m.group(2))
    return None


def extract_budget_from_body(text: str | None) -> tuple[Optional[int], Optional[int], Optional[str]]:
    """本文中の「予算」「報酬」ラベル付近から予算を抽出する。"""
    if not text:
        return None, None, None
    m = re.search(r"(予算|報酬|単価)[:：\s]*([0-9,，万円〜~\-\.]+)", text)
    if m:
        return parse_budget(m.group(2))
    return None, None, None


def extract_client_name(text: str | None) -> Optional[str]:
    """本文中の「クライアント名」「発注者」ラベルから名前を抽出する。"""
    if not text:
        return None
    m = re.search(r"(クライアント名|発注者|依頼主)[:：\s]*([^\n、。]+)", text)
    if m:
        return m.group(2).strip()
    return None


def extract_fields_from_body(body: str | None) -> dict:
    """案件本文から補助的に各項目を抽出し、辞書として返す。"""
    budget_min, budget_max, budget_text = extract_budget_from_body(body)
    return {
        "budget_min": budget_min,
        "budget_max": budget_max,
        "budget_text": budget_text,
        "deadline": extract_deadline(body),
        "job_type": extract_job_type(body),
        "applicant_count": extract_applicant_count(body),
        "recruitment_count": extract_recruitment_count(body),
        "client_name": extract_client_name(body),
    }
