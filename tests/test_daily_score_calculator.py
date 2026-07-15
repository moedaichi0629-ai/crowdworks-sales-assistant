"""デイリー優先スコア(daily_score_calculator)のテスト。"""
from __future__ import annotations

import datetime

from src.daily.daily_score_calculator import compute_daily_priority_score
from src.utils import now_jst_str


def _job(**overrides):
    job = {
        "title": "テスト案件", "body": "x" * 100, "applicant_count": 5,
        "client_rating": 4.0, "identity_verified": 1, "deadline": None,
        "published_at": now_jst_str(),
    }
    job.update(overrides)
    return job


def _analysis(**overrides):
    analysis = {
        "total_score": 70, "safety_score": 80, "risk_level": "low",
        "budget_evaluation": "fair", "missing_skills": [],
    }
    analysis.update(overrides)
    return analysis


def test_score_stays_within_0_100():
    low = compute_daily_priority_score(_job(applicant_count=100), _analysis(total_score=0, safety_score=0), 0, None)
    assert 0 <= low["score"] <= 100

    high = compute_daily_priority_score(
        _job(), _analysis(total_score=100, safety_score=100), 100, {"preparation_status": "応募準備完了"},
    )
    assert 0 <= high["score"] <= 100


def test_fresh_job_scores_higher_than_stale_job():
    fresh = compute_daily_priority_score(_job(published_at=now_jst_str()), _analysis(), 0, None)
    old_date = (datetime.datetime.now() - datetime.timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
    stale = compute_daily_priority_score(_job(published_at=old_date), _analysis(), 0, None)
    assert fresh["score"] > stale["score"]


def test_few_applicants_scores_higher_than_many():
    few = compute_daily_priority_score(_job(applicant_count=2), _analysis(), 0, None)
    many = compute_daily_priority_score(_job(applicant_count=25), _analysis(), 0, None)
    assert few["score"] > many["score"]
    assert any("応募人数が多い" in r for r in many["reasons"])
    assert any("少なめ" in r for r in few["reasons"])


def test_ready_draft_bonus_applied():
    no_draft = compute_daily_priority_score(_job(), _analysis(), 0, None)
    ready = compute_daily_priority_score(_job(), _analysis(), 0, {"preparation_status": "応募準備完了"})
    assert ready["score"] > no_draft["score"]
    assert any("応募準備完了" in r for r in ready["reasons"])


def test_missing_draft_penalized():
    result = compute_daily_priority_score(_job(), _analysis(), 0, None)
    assert any("営業文が未作成" in r for r in result["reasons"])


def test_medium_risk_penalized():
    low_risk = compute_daily_priority_score(_job(), _analysis(risk_level="low"), 0, None)
    medium_risk = compute_daily_priority_score(_job(), _analysis(risk_level="medium"), 0, None)
    assert medium_risk["score"] < low_risk["score"]
    assert any("危険度medium" in r for r in medium_risk["reasons"])


def test_weight_change_affects_score():
    default_result = compute_daily_priority_score(_job(), _analysis(total_score=100), 0, None)
    custom_weights = {
        "total_score": 0.9, "safety": 0.02, "freshness": 0.02, "deadline_proximity": 0.01,
        "applicant_scarcity": 0.01, "budget": 0.01, "client_trust": 0.01,
        "portfolio_match": 0.01, "draft_readiness": 0.01,
    }
    custom_result = compute_daily_priority_score(_job(), _analysis(total_score=100), 0, None, weights=custom_weights)
    assert custom_result["score"] != default_result["score"]
