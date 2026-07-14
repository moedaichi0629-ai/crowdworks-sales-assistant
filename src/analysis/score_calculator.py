"""総合スコアの計算・応募優先度の判定。"""
from __future__ import annotations

from src.config import (
    DEFAULT_PRIORITY_THRESHOLDS,
    DEFAULT_SCORE_WEIGHTS,
    PRIORITY_CANDIDATE,
    PRIORITY_HIGH,
    PRIORITY_REVIEW,
    PRIORITY_SKIP,
    PRIORITY_TOP,
)

WEIGHT_SUM_TOLERANCE = 0.01


def validate_weights(weights: dict) -> tuple[bool, float]:
    """重みの合計が100%(1.0)に近いか検証する。戻り値: (妥当か, 合計値)。"""
    total = sum(float(v) for v in weights.values())
    return abs(total - 1.0) <= WEIGHT_SUM_TOLERANCE, total


def _budget_evaluation_score(budget_evaluation: str) -> int:
    return {"low": 30, "fair": 60, "good": 90, "unknown": 50}.get(budget_evaluation, 50)


def _deadline_score(days_left: int | None) -> int:
    if days_left is None:
        return 50
    if days_left < 3:
        return 20
    if days_left < 7:
        return 50
    if days_left < 14:
        return 70
    return 90


def _applicant_score(applicant_count: int | None) -> int:
    if applicant_count is None:
        return 50
    if applicant_count >= 10:
        return 30
    if applicant_count <= 3:
        return 90
    return 60


def _client_trust_score(client_rating: float | None, identity_verified: bool | None) -> int:
    if client_rating is None:
        base = 50
    elif client_rating >= 4.5:
        base = 95
    elif client_rating >= 4.0:
        base = 80
    elif client_rating >= 3.5:
        base = 60
    else:
        base = 30
    if identity_verified:
        base = min(100, base + 5)
    return base


def _portfolio_match_score(portfolio_match_count: int) -> int:
    if portfolio_match_count >= 2:
        return 90
    if portfolio_match_count == 1:
        return 70
    return 40


def compute_total_score(
    ai_suitability_score: int | None,
    rule_based_score: int,
    safety_score: int,
    budget_evaluation: str,
    days_left: int | None,
    applicant_count: int | None,
    client_rating: float | None,
    identity_verified: bool | None,
    portfolio_match_count: int,
    weights: dict | None = None,
) -> int:
    """0〜100の総合スコアを算出する。AI未使用時はAI適合度の代わりにルールベーススコアを用いる。"""
    w = {**DEFAULT_SCORE_WEIGHTS, **(weights or {})}
    is_valid, total = validate_weights(w)
    if not is_valid:
        # 重みが不正な場合は既定値へフォールバックする（保存前チェックはUI側で別途警告する）
        w = DEFAULT_SCORE_WEIGHTS

    ai_component = ai_suitability_score if ai_suitability_score is not None else rule_based_score

    components = {
        "ai_suitability": ai_component,
        "rule_based": rule_based_score,
        "safety": safety_score,
        "budget": _budget_evaluation_score(budget_evaluation),
        "deadline": _deadline_score(days_left),
        "applicant_count": _applicant_score(applicant_count),
        "client_trust": _client_trust_score(client_rating, identity_verified),
        "portfolio_match": _portfolio_match_score(portfolio_match_count),
    }

    total_score = sum(components[key] * w.get(key, 0) for key in components)
    return max(0, min(100, round(total_score)))


def compute_priority(total_score: int, risk_level: str, thresholds: dict | None = None) -> str:
    """総合スコアと危険度から応募優先度を判定する。危険度が高い場合は優先度を強制的に下げる。"""
    t = {**DEFAULT_PRIORITY_THRESHOLDS, **(thresholds or {})}

    if total_score >= t["top"]:
        priority = PRIORITY_TOP
    elif total_score >= t["high"]:
        priority = PRIORITY_HIGH
    elif total_score >= t["candidate"]:
        priority = PRIORITY_CANDIDATE
    elif total_score >= t["review"]:
        priority = PRIORITY_REVIEW
    else:
        priority = PRIORITY_SKIP

    if risk_level == "critical":
        return PRIORITY_SKIP
    if risk_level == "high" and priority in (PRIORITY_TOP, PRIORITY_HIGH, PRIORITY_CANDIDATE):
        return PRIORITY_REVIEW

    return priority
