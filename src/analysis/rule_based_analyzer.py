"""ルールベースによる案件の一次判定（0〜100点）。

AI APIを使わなくても最低限の判定ができるよう、この結果単体でも
（AI分析なしの場合の）フォールバック総合スコアの主要素として使用する。
"""
from __future__ import annotations

import datetime as dt

from src.config import DEFAULT_RULE_WEIGHTS, RULE_APPLICANT_FEW_COUNT, RULE_APPLICANT_MANY_COUNT
from src.config import RULE_BODY_VAGUE_LENGTH, RULE_BUDGET_LOW_THRESHOLD_YEN
from src.config import RULE_CLIENT_RATING_HIGH, RULE_CLIENT_RATING_LOW, RULE_DEADLINE_TIGHT_DAYS
from src.config import RULE_KEYWORD_BONUS_MAX, RULE_KEYWORD_BONUS_WEIGHT
from src.config import RULE_KEYWORD_PENALTY_MAX, RULE_KEYWORD_PENALTY_WEIGHT


def _job_text(job: dict) -> str:
    return " ".join(
        str(job.get(field) or "") for field in ("title", "description", "body", "category")
    )


def days_until_deadline(deadline: str | None) -> int | None:
    if not deadline:
        return None
    try:
        deadline_date = dt.datetime.strptime(deadline[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    return (deadline_date - dt.date.today()).days


def analyze_rule_based(
    job: dict,
    skills: list[dict],
    portfolios: list[dict],
    difficult_conditions: list[str],
    exclude_keywords: list[str],
    weights: dict | None = None,
    bonus_keywords: list[str] | None = None,
    penalty_keywords: list[str] | None = None,
) -> dict:
    """ルールベース一次判定を実行する。

    戻り値: {
        "score": int, "breakdown": [{"label": str, "delta": int}],
        "breakdown_labels": [str], "matched_skills": [str], "matched_portfolio_titles": [str],
    }
    """
    w = {**DEFAULT_RULE_WEIGHTS, **(weights or {})}
    text = _job_text(job)
    text_lower = text.lower()

    score = 50  # 基準点（不明点が多い場合はここから加減点する）
    breakdown: list[dict] = []

    def add(label: str, delta: int) -> None:
        nonlocal score
        if delta == 0:
            return
        score += delta
        breakdown.append({"label": label, "delta": delta})

    # --- スキルキーワード一致 ---
    matched_skills: list[str] = []
    for skill in skills:
        name = skill.get("skill_name") or ""
        if name and name.lower() in text_lower:
            matched_skills.append(name)
    skill_bonus = min(len(matched_skills) * w["skill_match_per_hit"], w["skill_match_max"])
    if matched_skills:
        add(f"スキル一致 {len(matched_skills)}件（{', '.join(matched_skills[:5])}）", skill_bonus)

    # --- 制作実績との一致 ---
    matched_portfolio_titles: list[str] = []
    for portfolio in portfolios:
        keywords = [portfolio.get("title", "")] + (portfolio.get("technologies") or []) + (portfolio.get("skills") or [])
        if any(kw and kw.lower() in text_lower for kw in keywords):
            matched_portfolio_titles.append(portfolio["title"])
    if matched_portfolio_titles:
        add(f"関連制作実績あり（{', '.join(matched_portfolio_titles[:3])}）", w["portfolio_match_bonus"])

    # --- 対応困難条件への該当 ---
    difficult_hits = [c for c in difficult_conditions if c and c in text]
    if difficult_hits:
        add(f"対応困難条件に該当（{', '.join(difficult_hits[:3])}）", -w["difficult_condition_penalty"] * len(difficult_hits))

    # --- 除外キーワードへの該当 ---
    excluded_hits = [k for k in exclude_keywords if k and k in text]
    if excluded_hits or job.get("excluded_keyword"):
        add("除外キーワードに該当", -w["exclude_keyword_penalty"])

    # --- 加点・減点キーワード（設定画面で編集可能） ---
    bonus_hits = [k for k in (bonus_keywords or []) if k and k in text]
    if bonus_hits:
        add(f"加点キーワードに該当（{', '.join(bonus_hits[:3])}）", min(len(bonus_hits) * RULE_KEYWORD_BONUS_WEIGHT, RULE_KEYWORD_BONUS_MAX))

    penalty_hits = [k for k in (penalty_keywords or []) if k and k in text]
    if penalty_hits:
        add(f"減点キーワードに該当（{', '.join(penalty_hits[:3])}）", -min(len(penalty_hits) * RULE_KEYWORD_PENALTY_WEIGHT, RULE_KEYWORD_PENALTY_MAX))

    # --- 予算の妥当性 ---
    budget_max = job.get("budget_max")
    if budget_max is not None:
        if budget_max < RULE_BUDGET_LOW_THRESHOLD_YEN:
            add("予算が低い", -w["budget_low_penalty"])
        elif budget_max >= RULE_BUDGET_LOW_THRESHOLD_YEN * 5:
            add("予算が良い", w["budget_good_bonus"])

    # --- 納期までの残り日数 ---
    days_left = days_until_deadline(job.get("deadline"))
    if days_left is not None:
        if days_left < RULE_DEADLINE_TIGHT_DAYS:
            add("希望納期が短い", -w["deadline_tight_penalty"])
        elif days_left >= 14:
            add("納期に余裕がある", w["deadline_ample_bonus"])

    # --- 応募人数 ---
    applicant_count = job.get("applicant_count")
    if applicant_count is not None:
        if applicant_count >= RULE_APPLICANT_MANY_COUNT:
            add("応募人数が多い", -w["applicant_many_penalty"])
        elif applicant_count <= RULE_APPLICANT_FEW_COUNT:
            add("応募人数が少ない", w["applicant_few_bonus"])

    # --- クライアント評価 ---
    client_rating = job.get("client_rating")
    if client_rating is not None:
        if client_rating >= RULE_CLIENT_RATING_HIGH:
            add("クライアント評価が高い", w["client_rating_high_bonus"])
        elif client_rating < RULE_CLIENT_RATING_LOW:
            add("クライアント評価が低い", -w["client_rating_low_penalty"])

    # --- 本人確認の有無 ---
    if job.get("identity_verified"):
        add("本人確認済み", w["identity_verified_bonus"])

    # --- 案件本文の具体性 ---
    body = job.get("body") or job.get("description") or ""
    if len(body.strip()) < RULE_BODY_VAGUE_LENGTH:
        add("案件本文の情報が少ない", -w["body_vague_penalty"])
    elif any(k in body for k in ("成果物", "納品", "要件", "仕様", "作業内容")):
        add("作業内容・成果物が明確", w["body_concrete_bonus"])

    score = max(0, min(100, score))

    breakdown_labels = [f"{b['label']}：{'+' if b['delta'] >= 0 else ''}{b['delta']}" for b in breakdown]

    return {
        "score": score,
        "breakdown": breakdown,
        "breakdown_labels": breakdown_labels,
        "matched_skills": matched_skills,
        "matched_portfolio_titles": matched_portfolio_titles,
    }
