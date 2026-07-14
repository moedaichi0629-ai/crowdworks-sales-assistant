"""営業文生成AIレスポンス解析(application_response_parser)のテスト。"""
from __future__ import annotations

import json

import pytest

from src.ai.response_parser import ResponseParseError
from src.application.application_response_parser import parse_application_response

_VALID_PAYLOAD = {
    "application_title": "テスト応募",
    "opening": "はじめまして。",
    "full_message": "本文です。",
    "short_message": "短縮版です。",
    "proposed_price": 10000,
    "proposed_delivery_days": 7,
    "confidence": 80,
}


def test_parse_plain_json():
    result = parse_application_response(json.dumps(_VALID_PAYLOAD, ensure_ascii=False))
    assert result.application_title == "テスト応募"
    assert result.proposed_price == 10000
    assert result.confidence == 80


def test_parse_fenced_json():
    text = f"```json\n{json.dumps(_VALID_PAYLOAD, ensure_ascii=False)}\n```"
    result = parse_application_response(text)
    assert result.full_message == "本文です。"


def test_parse_with_surrounding_prose():
    text = f"以下が結果です。\n{json.dumps(_VALID_PAYLOAD, ensure_ascii=False)}\nご確認ください。"
    result = parse_application_response(text)
    assert result.short_message == "短縮版です。"


def test_parse_missing_fields_filled_with_defaults():
    result = parse_application_response(json.dumps({"full_message": "本文のみ"}))
    assert result.proposed_price == 0
    assert result.skills_to_highlight == []
    assert result.warnings == []


def test_parse_clamps_confidence_out_of_range():
    payload = {**_VALID_PAYLOAD, "confidence": 500}
    result = parse_application_response(json.dumps(payload))
    assert result.confidence == 100


def test_parse_invalid_json_raises():
    with pytest.raises(ResponseParseError):
        parse_application_response("これはJSONではありません")


def test_parse_invalid_portfolio_ids_dropped():
    payload = {**_VALID_PAYLOAD, "portfolio_ids": [1, "abc", 2, None]}
    result = parse_application_response(json.dumps(payload))
    assert result.portfolio_ids == [1, 2]
