"""総合スコア計算・応募優先度判定(score_calculator)のテスト。"""
from __future__ import annotations

from src.analysis.score_calculator import compute_priority, compute_total_score, validate_weights
from src.config import DEFAULT_SCORE_WEIGHTS


def test_validate_weights_sum_100_percent():
    is_valid, total = validate_weights(DEFAULT_SCORE_WEIGHTS)
    assert is_valid is True
    assert abs(total - 1.0) < 1e-6


def test_validate_weights_invalid_sum():
    is_valid, total = validate_weights({"a": 0.5, "b": 0.2})
    assert is_valid is False
    assert abs(total - 0.7) < 1e-6


def test_compute_total_score_weighted_high_inputs():
    score = compute_total_score(
        ai_suitability_score=90, rule_based_score=80, safety_score=100,
        budget_evaluation="good", days_left=20, applicant_count=2, client_rating=4.8,
        identity_verified=True, portfolio_match_count=2,
    )
    assert 0 <= score <= 100
    assert score > 70


def test_compute_total_score_invalid_weights_falls_back_to_default():
    score_default = compute_total_score(
        90, 80, 100, "good", 20, 2, 4.8, True, 2, weights=DEFAULT_SCORE_WEIGHTS,
    )
    score_invalid_weights = compute_total_score(
        90, 80, 100, "good", 20, 2, 4.8, True, 2, weights={"ai_suitability": 0.9},
    )
    assert score_default == score_invalid_weights


def test_compute_total_score_without_ai_uses_rule_score():
    score = compute_total_score(
        ai_suitability_score=None, rule_based_score=70, safety_score=100,
        budget_evaluation="fair", days_left=10, applicant_count=5, client_rating=None,
        identity_verified=None, portfolio_match_count=0,
    )
    assert 0 <= score <= 100


def test_compute_priority_boundaries():
    assert compute_priority(95, "low") == "最優先"
    assert compute_priority(85, "low") == "優先"
    assert compute_priority(75, "low") == "応募候補"
    assert compute_priority(65, "low") == "要確認"
    assert compute_priority(30, "low") == "見送り候補"


def test_compute_priority_high_risk_forces_downgrade():
    assert compute_priority(95, "critical") == "見送り候補"
    assert compute_priority(95, "high") == "要確認"
    assert compute_priority(30, "high") == "見送り候補"
