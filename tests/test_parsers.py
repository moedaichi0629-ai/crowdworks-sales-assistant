"""予算・日付・本文抽出パーサーのテスト。"""
from __future__ import annotations

from src.parsers import (
    extract_applicant_count,
    extract_deadline,
    extract_fields_from_body,
    parse_budget,
    parse_date,
)


def test_parse_budget_range_in_man_yen():
    budget_min, budget_max, text = parse_budget("3万円〜5万円")
    assert budget_min == 30000
    assert budget_max == 50000
    assert text == "3万円〜5万円"


def test_parse_budget_single_value():
    budget_min, budget_max, _ = parse_budget("50,000円")
    assert budget_min == 50000
    assert budget_max == 50000


def test_parse_budget_hourly():
    budget_min, budget_max, _ = parse_budget("時給1,500円")
    assert budget_min == 1500
    assert budget_max == 1500


def test_parse_budget_empty_returns_none():
    assert parse_budget(None) == (None, None, None)
    assert parse_budget("") == (None, None, None)


def test_parse_date_japanese_format():
    assert parse_date("2026年7月20日") == "2026-07-20"


def test_parse_date_slash_format():
    assert parse_date("2026/07/20") == "2026-07-20"


def test_parse_date_unparsable_returns_none():
    assert parse_date("応相談") is None
    assert parse_date(None) is None


def test_extract_applicant_count():
    assert extract_applicant_count("応募人数3名の案件です") == 3


def test_extract_deadline_from_body():
    body = "応募期限: 2026年8月10日までにご連絡ください。"
    assert extract_deadline(body) == "2026-08-10"


def test_extract_fields_from_body_full():
    body = "予算:20万円〜40万円 応募期限:2026年8月10日 応募人数:3 採用人数:1 クライアント名:株式会社サンプル"
    fields = extract_fields_from_body(body)
    assert fields["budget_min"] == 200000
    assert fields["budget_max"] == 400000
    assert fields["deadline"] == "2026-08-10"
    assert fields["applicant_count"] == 3
    assert fields["recruitment_count"] == 1
    assert fields["client_name"] == "株式会社サンプル"
