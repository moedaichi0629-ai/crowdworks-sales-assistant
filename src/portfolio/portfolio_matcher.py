"""案件ごとに関連度の高いポートフォリオ（制作実績）を自動選択する。

デザイン案件ではforiioのデザインポートフォリオを、AI・Web開発案件では
AI・開発ポートフォリオ／GitHubを優先し、AI×デザイン複合案件では両方を候補にする
（要件の「ポートフォリオ選択の基本ルール」に対応）。

関連性が低いポートフォリオは無理に選択せず、該当がない場合は
「関連実績なし」として扱う（虚偽の実績を営業文へ書かせないため）。
"""
from __future__ import annotations

from src.portfolio.portfolio_category_classifier import classify_job_category

MAX_SELECTIONS = 3
MIN_RELEVANCE_THRESHOLD = 35

_SKILL_MATCH_WEIGHT = 8
_SKILL_MATCH_MAX = 40
_CATEGORY_KEYWORD_WEIGHT = 10
_CATEGORY_KEYWORD_MAX = 20


def _job_text(job: dict) -> str:
    return " ".join(
        str(job.get(field) or "") for field in ("title", "category", "description", "body")
    )


def _portfolio_keywords(portfolio: dict) -> list[str]:
    keywords: list[str] = []
    for field in ("technology_keywords", "design_tools", "skills", "technologies", "subcategories"):
        keywords.extend(portfolio.get(field) or [])
    return [k for k in keywords if k]


def compute_relevance_score(job: dict, portfolio: dict, job_classification: dict | None = None) -> dict:
    """1件のポートフォリオについて、案件との関連度(0〜100)と選択理由を算出する。"""
    if not portfolio.get("is_active", True):
        return {"score": 0, "reasons": ["非公開のため対象外"], "matched_skills": []}

    text = _job_text(job)
    text_lower = text.lower()
    classification = job_classification or classify_job_category(job)

    score = 0
    reasons: list[str] = []

    # --- 使用技術・キーワードとの一致 ---
    keywords = _portfolio_keywords(portfolio)
    matched = sorted({kw for kw in keywords if kw and kw.lower() in text_lower})
    if matched:
        bonus = min(len(matched) * _SKILL_MATCH_WEIGHT, _SKILL_MATCH_MAX)
        score += bonus
        reasons.append(f"案件内容と一致するキーワード（{', '.join(matched[:5])}）")

    # --- 対象案件カテゴリとの一致 ---
    target_categories = portfolio.get("target_job_categories") or []
    matched_categories = sorted({c for c in target_categories if c and (c in text or any(part in text for part in c.split("・")))})
    if matched_categories:
        bonus = min(len(matched_categories) * _CATEGORY_KEYWORD_WEIGHT, _CATEGORY_KEYWORD_MAX)
        score += bonus
        reasons.append(f"対象案件カテゴリと一致（{', '.join(matched_categories[:3])}）")

    # --- デザイン案件 / 開発案件 / AI×デザイン複合案件の該当 ---
    if classification["is_design"] and portfolio.get("for_design"):
        score += 30
        reasons.append("デザイン案件と一致し、デザイン実績として最優先候補")
    if classification["is_development"] and portfolio.get("for_development"):
        score += 25
        reasons.append("AI・Web開発案件と一致")
    if classification["is_ai_design"] and portfolio.get("for_ai_design"):
        score += 20
        reasons.append("AI×デザイン複合案件の実績として提示可能")

    # --- 公開URL・GitHub URLの有無 ---
    if portfolio.get("portfolio_url"):
        score += 5
        reasons.append("公開URLがあり実際の制作物を確認できる")
    if portfolio.get("github_url"):
        score += 5
        reasons.append("GitHubでソースコード・開発履歴を確認できる")

    # --- 優先度設定による微調整 ---
    score += min(int(portfolio.get("priority", 50)) * 0.1, 10)

    score = max(0, min(100, round(score)))
    if score < MIN_RELEVANCE_THRESHOLD:
        reasons = ["関連性が低いため通常は選択しない"]

    return {"score": score, "reasons": reasons, "matched_skills": matched}


def select_portfolios(
    job: dict,
    portfolios: list[dict],
    max_selections: int = MAX_SELECTIONS,
    min_score_threshold: int = MIN_RELEVANCE_THRESHOLD,
    manual_selected_ids: list[int] | None = None,
) -> list[dict]:
    """案件と関連度の高いポートフォリオを最大 max_selections 件、自動選択する。

    `manual_selected_ids` が指定された場合はその順序・内容を優先し、
    自動選択結果は参考スコアとしてのみ付与する（手動選択の保持）。

    戻り値: [{"portfolio_id", "title", "relevance_score", "matched_skills",
              "matched_category", "match_reason", "is_selected", "selection_order"}]
             関連度スコアの高い順。
    """
    classification = classify_job_category(job)
    active_portfolios = [p for p in portfolios if p.get("is_active", True)]

    scored: list[dict] = []
    for portfolio in active_portfolios:
        result = compute_relevance_score(job, portfolio, classification)
        matched_category = (
            "design" if classification["is_design"] and portfolio.get("for_design")
            else "development" if classification["is_development"] and portfolio.get("for_development")
            else "ai_design" if classification["is_ai_design"] and portfolio.get("for_ai_design")
            else "general"
        )
        scored.append({
            "portfolio_id": portfolio["id"],
            "title": portfolio["title"],
            "relevance_score": result["score"],
            "matched_skills": result["matched_skills"],
            "matched_category": matched_category,
            "match_reason": "\n".join(f"・{r}" for r in result["reasons"]),
            "is_selected": False,
            "selection_order": None,
        })

    scored.sort(key=lambda x: x["relevance_score"], reverse=True)

    if manual_selected_ids:
        id_to_item = {item["portfolio_id"]: item for item in scored}
        for order, pid in enumerate(manual_selected_ids):
            if pid in id_to_item:
                id_to_item[pid]["is_selected"] = True
                id_to_item[pid]["selection_order"] = order
        return scored

    order = 0
    for item in scored:
        if item["relevance_score"] >= min_score_threshold and order < max_selections:
            item["is_selected"] = True
            item["selection_order"] = order
            order += 1

    return scored
