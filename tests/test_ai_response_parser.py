"""AIレスポンス解析(response_parser)のテスト。"""
from __future__ import annotations

import json

import pytest

from src.ai.response_parser import ResponseParseError, extract_json, parse_ai_response


def test_parse_normal_json():
    text = json.dumps({"suitability_score": 80})
    assert extract_json(text)["suitability_score"] == 80


def test_parse_markdown_fenced_json():
    text = '```json\n{"suitability_score": 70}\n```'
    assert extract_json(text)["suitability_score"] == 70


def test_parse_json_with_surrounding_text():
    text = '以下が分析結果です。\n{"suitability_score": 60}\nご確認ください。'
    assert extract_json(text)["suitability_score"] == 60


def test_parse_json_with_trailing_comma():
    text = '{"a": 1, "b": [1, 2,],}'
    data = extract_json(text)
    assert data["a"] == 1
    assert data["b"] == [1, 2]


def test_parse_json_missing_fields_uses_defaults():
    text = json.dumps({"suitability_score": 55})
    result = parse_ai_response(text)
    assert result.suitability_score == 55
    assert result.recommendation == "consider"
    assert result.matched_skills == []


def test_parse_invalid_json_raises():
    with pytest.raises(ResponseParseError):
        extract_json("これはJSONではありません。分析できませんでした。")


def test_parse_empty_response_raises():
    with pytest.raises(ResponseParseError):
        extract_json("")


def test_parse_score_out_of_range_is_clamped():
    text = json.dumps({"suitability_score": 150, "confidence": -10, "safety_score": 999})
    result = parse_ai_response(text)
    assert result.suitability_score == 100
    assert result.confidence == 0
    assert result.safety_score == 100


def test_parse_invalid_enum_value_falls_back_to_safe_default():
    text = json.dumps({"recommendation": "invalid_value", "risk_level": "invalid", "difficulty": "invalid"})
    result = parse_ai_response(text)
    assert result.recommendation == "consider"
    assert result.risk_level == "low"
    assert result.difficulty == "intermediate"
