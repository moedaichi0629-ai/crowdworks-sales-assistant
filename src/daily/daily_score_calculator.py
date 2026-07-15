"""本日の応募候補選定で使う「デイリー優先スコア」(0〜100)を計算する。

第2段階の総合スコア(score_calculator)とは目的が異なり、「今日どの案件から応募すべきか」を
新着度・応募期限・応募人数の少なさ・応募準備状況なども加味して判定するためのスコアである。
"""
from __future__ import annotations

from datetime import datetime

from src.config import (
    DAILY_DEADLINE_VERY_CLOSE_DAYS,
    DAILY_HIGH_CLIENT_RATING_THRESHOLD,
    DAILY_HIGH_PORTFOLIO_MATCH_THRESHOLD,
    DAILY_MANY_APPLICANTS_THRESHOLD,
    DAILY_MISSING_SKILLS_MANY_COUNT,
    DAILY_SCORE_BONUS_POINTS,
    DAILY_SCORE_PENALTY_POINTS,
    DEFAULT_DAILY_SCORE_WEIGHTS,
    PREP_STATUS_NONE,
    PREP_STATUS_READY,
    RULE_BODY_VAGUE_LENGTH,
)
from src.utils import now_jst


def _budget_component(budget_evaluation: str | None) -> int:
    return {"low": 30, "fair": 60, "good": 90}.get(budget_evaluation, 50)


def _client_trust_component(client_rating: float | None, identity_verified) -> int:
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


def _parse_datetime(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        pass
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d")
    except ValueError:
        return None


def _hours_since(text: str | None) -> float | None:
    published = _parse_datetime(text)
    if published is None:
        return None
    now = now_jst().replace(tzinfo=None)
    delta = now - published
    return max(0.0, delta.total_seconds() / 3600)


def _freshness_component(job: dict) -> tuple[int, float | None]:
    hours = _hours_since(job.get("published_at") or job.get("collected_at"))
    if hours is None:
        return 50, None
    if hours <= 24:
        return 100, hours
    if hours <= 48:
        return 80, hours
    if hours <= 72:
        return 60, hours
    return 30, hours


def _days_left(deadline: str | None) -> int | None:
    if not deadline:
        return None
    try:
        deadline_date = datetime.strptime(deadline[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    return (deadline_date - now_jst().date()).days


def _deadline_component(days_left: int | None) -> int:
    if days_left is None:
        return 50
    if days_left <= DAILY_DEADLINE_VERY_CLOSE_DAYS:
        return 40
    if days_left <= 5:
        return 90
    if days_left <= 10:
        return 70
    return 50


def _applicant_component(applicant_count: int | None) -> int:
    if applicant_count is None:
        return 50
    if applicant_count <= 3:
        return 100
    if applicant_count <= 10:
        return 70
    if applicant_count <= 20:
        return 40
    return 20


def _draft_readiness_component(preparation_status: str | None) -> int:
    if preparation_status == PREP_STATUS_READY:
        return 100
    if preparation_status and preparation_status != PREP_STATUS_NONE:
        return 70
    return 20


def compute_daily_priority_score(
    job: dict,
    analysis: dict | None,
    portfolio_relevance_score: int = 0,
    draft: dict | None = None,
    weights: dict | None = None,
) -> dict:
    """0〜100の「デイリー優先スコア」と選定理由を算出する。

    戻り値: {"score": int, "reasons": [str]}
    """
    w = {**DEFAULT_DAILY_SCORE_WEIGHTS, **(weights or {})}
    analysis = analysis or {}

    total_score = analysis.get("total_score")
    safety_score = analysis.get("safety_score")
    risk_level = analysis.get("risk_level")
    budget_evaluation = analysis.get("budget_evaluation")
    missing_skills = analysis.get("missing_skills") or []

    freshness_component, hours_since = _freshness_component(job)
    days_left = _days_left(job.get("deadline"))
    applicant_count = job.get("applicant_count")
    preparation_status = (draft or {}).get("preparation_status")

    components = {
        "total_score": total_score if total_score is not None else 50,
        "safety": safety_score if safety_score is not None else 50,
        "freshness": freshness_component,
        "deadline_proximity": _deadline_component(days_left),
        "applicant_scarcity": _applicant_component(applicant_count),
        "budget": _budget_component(budget_evaluation),
        "client_trust": _client_trust_component(job.get("client_rating"), job.get("identity_verified")),
        "portfolio_match": portfolio_relevance_score,
        "draft_readiness": _draft_readiness_component(preparation_status),
    }
    base_score = sum(components[key] * w.get(key, 0) for key in components)

    reasons: list[str] = []
    if total_score is not None:
        reasons.append(f"総合スコア{total_score}点")
    if safety_score is not None:
        reasons.append(f"安全度{safety_score}点")
    if hours_since is not None:
        if hours_since <= 24:
            reasons.append(f"掲載から{int(hours_since)}時間以内")
        else:
            reasons.append(f"掲載から約{int(hours_since // 24)}日経過")

    adjustment = 0

    if applicant_count is not None and applicant_count <= 10:
        adjustment += DAILY_SCORE_BONUS_POINTS["few_applicants"]
        reasons.append(f"応募人数{applicant_count}人（少なめ）")
    elif applicant_count is not None and applicant_count >= DAILY_MANY_APPLICANTS_THRESHOLD:
        adjustment -= DAILY_SCORE_PENALTY_POINTS["many_applicants"]
        reasons.append(f"応募人数が多い（{applicant_count}人）")

    if preparation_status == PREP_STATUS_READY:
        adjustment += DAILY_SCORE_BONUS_POINTS["ready_for_application"]
        reasons.append("応募準備完了")
    elif preparation_status and preparation_status != PREP_STATUS_NONE:
        adjustment += DAILY_SCORE_BONUS_POINTS["draft_created"]
        reasons.append("営業文作成済み")
    else:
        adjustment -= DAILY_SCORE_PENALTY_POINTS["draft_missing"]
        reasons.append("営業文が未作成")

    if hours_since is not None and hours_since <= 24:
        adjustment += DAILY_SCORE_BONUS_POINTS["posted_within_24h"]

    if job.get("identity_verified"):
        adjustment += DAILY_SCORE_BONUS_POINTS["identity_verified"]
        reasons.append("本人確認済み")

    client_rating = job.get("client_rating")
    if client_rating is not None and client_rating >= DAILY_HIGH_CLIENT_RATING_THRESHOLD:
        adjustment += DAILY_SCORE_BONUS_POINTS["high_client_rating"]
        reasons.append(f"クライアント評価{client_rating}（4.5以上）")

    if portfolio_relevance_score >= DAILY_HIGH_PORTFOLIO_MATCH_THRESHOLD:
        adjustment += DAILY_SCORE_BONUS_POINTS["high_portfolio_match"]
        reasons.append(f"関連ポートフォリオとの一致度{portfolio_relevance_score}点")
    elif 0 < portfolio_relevance_score < 35:
        adjustment -= DAILY_SCORE_PENALTY_POINTS["low_portfolio_match"]
        reasons.append("ポートフォリオとの関連性が低い")

    if days_left is not None and days_left <= DAILY_DEADLINE_VERY_CLOSE_DAYS:
        adjustment -= DAILY_SCORE_PENALTY_POINTS["deadline_very_close"]
        reasons.append("応募期限が極端に近い")

    if len(missing_skills) >= DAILY_MISSING_SKILLS_MANY_COUNT:
        adjustment -= DAILY_SCORE_PENALTY_POINTS["missing_skills_many"]
        reasons.append("不足スキルが多い")

    if budget_evaluation == "low":
        adjustment -= DAILY_SCORE_PENALTY_POINTS["low_budget"]
        reasons.append("予算が低い")

    body_len = len((job.get("body") or job.get("description") or "").strip())
    if body_len and body_len < RULE_BODY_VAGUE_LENGTH:
        adjustment -= DAILY_SCORE_PENALTY_POINTS["vague_body"]
        reasons.append("案件内容が曖昧")

    if risk_level == "medium":
        adjustment -= DAILY_SCORE_PENALTY_POINTS["medium_risk"]
        reasons.append("危険度medium")

    score = max(0, min(100, round(base_score + adjustment)))
    return {"score": score, "reasons": reasons}
