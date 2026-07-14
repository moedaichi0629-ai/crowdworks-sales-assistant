"""営業文生成の停止条件・AI出力検証(application_validator)のテスト。"""
from __future__ import annotations

from src.application.application_validator import check_stop_conditions, validate_application_message


def test_stops_on_critical_risk_level():
    job = {"title": "案件", "body": "詳細な案件内容がここに書かれています。" * 3}
    analysis = {"risk_level": "critical", "safety_score": 90}
    result = check_stop_conditions(job, analysis)
    assert result["should_stop"] is True


def test_stops_on_low_safety_score():
    job = {"title": "案件", "body": "詳細な案件内容がここに書かれています。" * 3}
    analysis = {"risk_level": "low", "safety_score": 10}
    result = check_stop_conditions(job, analysis)
    assert result["should_stop"] is True


def test_stops_on_empty_body():
    job = {"title": "案件", "body": ""}
    result = check_stop_conditions(job, None)
    assert result["should_stop"] is True


def test_stops_on_material_purchase_keyword():
    job = {"title": "案件", "body": "教材購入をお願いします。" * 3}
    result = check_stop_conditions(job, None)
    assert result["should_stop"] is True


def test_stops_on_excluded_condition_match():
    job = {"title": "案件", "body": "この案件では週5日常駐が必須です。詳細説明をここに記載します。"}
    profile = {"difficult_conditions": {"excluded_conditions": ["週5日常駐"]}}
    result = check_stop_conditions(job, None, profile)
    assert result["should_stop"] is True


def test_does_not_stop_on_normal_job():
    job = {"title": "AI開発案件", "body": "AIチャットボットを開発してください。要件は追ってご連絡します。"}
    analysis = {"risk_level": "low", "safety_score": 95}
    result = check_stop_conditions(job, analysis)
    assert result["should_stop"] is False
    assert result["reasons"] == []


def test_validate_message_removes_disallowed_url():
    allowed = {"https://example.com/portfolio"}
    result = validate_application_message(
        "実績はこちらです: https://example.com/portfolio と https://evil.example.com/",
        "短縮版", allowed,
    )
    assert "evil.example.com" not in result["full_message"]
    assert "example.com/portfolio" in result["full_message"]
    assert result["warnings"]


def test_validate_message_flags_guarantee_phrase():
    result = validate_application_message("必ず成果を出します。", "短縮版", set())
    assert any("保証" in w or "必ず成果" in w for w in result["warnings"])


def test_validate_message_flags_unverified_real_job_claim():
    result = validate_application_message("実務経験が豊富です。", "短縮版", set(), profile_skills=[])
    assert any("実務経験" in w for w in result["warnings"])


def test_validate_message_no_warning_when_real_job_experience_registered():
    skills = [{"skill_name": "Python", "experience_type": "実案件"}]
    result = validate_application_message("実務経験が豊富です。", "短縮版", set(), profile_skills=skills)
    assert not any("実務経験" in w for w in result["warnings"])
