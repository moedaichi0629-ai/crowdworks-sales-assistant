"""ルールベース一次判定(rule_based_analyzer)のテスト。"""
from __future__ import annotations

from src.analysis.rule_based_analyzer import analyze_rule_based


def test_skill_match_bonus():
    job = {"title": "Python開発案件", "body": "PythonとStreamlitを使った開発をお願いします。" * 3, "description": ""}
    skills = [{"skill_name": "Python"}, {"skill_name": "Streamlit"}, {"skill_name": "Java"}]
    result = analyze_rule_based(job, skills, [], [], [])
    assert "Python" in result["matched_skills"]
    assert "Streamlit" in result["matched_skills"]
    assert "Java" not in result["matched_skills"]
    assert any(d["delta"] > 0 for d in result["breakdown"] if "スキル一致" in d["label"])


def test_difficult_condition_penalty():
    job_bad = {"title": "急募", "body": "週5日常駐必須の案件です。" * 3, "description": ""}
    job_good = {"title": "通常案件", "body": "リモートで対応可能な案件です。" * 3, "description": ""}
    result_bad = analyze_rule_based(job_bad, [], [], ["週5日常駐"], [])
    result_good = analyze_rule_based(job_good, [], [], ["週5日常駐"], [])
    assert result_bad["score"] < result_good["score"]


def test_exclude_keyword_penalty():
    job = {"title": "教材購入が必要な案件", "body": "教材購入が必要です。" * 3, "description": ""}
    result_with = analyze_rule_based(job, [], [], [], ["教材購入"])
    result_without = analyze_rule_based(job, [], [], [], [])
    assert result_with["score"] < result_without["score"]


def test_budget_evaluation_low_penalty():
    job_low = {"title": "案件", "body": "x" * 60, "budget_max": 3000}
    job_none = {"title": "案件", "body": "x" * 60, "budget_max": None}
    r_low = analyze_rule_based(job_low, [], [], [], [])
    r_none = analyze_rule_based(job_none, [], [], [], [])
    assert r_low["score"] < r_none["score"]


def test_applicant_count_evaluation():
    job_many = {"title": "案件", "body": "x" * 60, "applicant_count": 20}
    job_few = {"title": "案件", "body": "x" * 60, "applicant_count": 2}
    r_many = analyze_rule_based(job_many, [], [], [], [])
    r_few = analyze_rule_based(job_few, [], [], [], [])
    assert r_few["score"] > r_many["score"]


def test_identity_verified_evaluation():
    job_verified = {"title": "案件", "body": "x" * 60, "identity_verified": 1}
    job_unverified = {"title": "案件", "body": "x" * 60, "identity_verified": 0}
    r_v = analyze_rule_based(job_verified, [], [], [], [])
    r_u = analyze_rule_based(job_unverified, [], [], [], [])
    assert r_v["score"] > r_u["score"]


def test_empty_body_does_not_error():
    job = {"title": "", "body": "", "description": ""}
    result = analyze_rule_based(job, [], [], [], [])
    assert 0 <= result["score"] <= 100


def test_score_stays_within_0_to_100():
    job = {
        "title": "危険案件" * 10, "body": "x" * 5,
        "excluded_keyword": "該当", "budget_max": 100, "applicant_count": 999,
        "client_rating": 1.0, "identity_verified": 0,
    }
    result = analyze_rule_based(
        job, [], [], ["週5日常駐", "出社必須", "電話営業"], ["教材購入", "初期費用", "無報酬テスト"],
    )
    assert 0 <= result["score"] <= 100


def test_bonus_and_penalty_keywords():
    job = {"title": "案件", "body": "リモートで在宅勤務が可能です。" * 3, "description": ""}
    result_with_bonus = analyze_rule_based(job, [], [], [], [], bonus_keywords=["リモート", "在宅"])
    result_without_bonus = analyze_rule_based(job, [], [], [], [], bonus_keywords=[])
    assert result_with_bonus["score"] > result_without_bonus["score"]
