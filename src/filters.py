"""案件一覧の絞り込み・並べ替えロジック（pandas DataFrameを対象とする）。"""
from __future__ import annotations

import pandas as pd

SORT_OPTIONS = {
    "新着順": ("created_at", False),
    "取得日時が新しい順": ("collected_at", False),
    "応募期限が近い順": ("deadline", True),
    "予算が高い順": ("budget_max", False),
    "応募人数が少ない順": ("applicant_count", True),
    "クライアント評価が高い順": ("client_rating", False),
}

# 分析結果一覧ページ用の並べ替え基準（案件一覧のSORT_OPTIONSと合わせて使用する）
ANALYSIS_SORT_OPTIONS = {
    "総合スコアが高い順": ("total_score", False),
    "AI適合度が高い順": ("ai_suitability_score", False),
    "安全度が高い順": ("safety_score", False),
    "予算が高い順": ("budget_max", False),
    "応募人数が少ない順": ("applicant_count", True),
    "掲載日時が新しい順": ("published_at", False),
    "応募期限が近い順": ("deadline", True),
    "分析日時が新しい順": ("analyzed_at", False),
}


def apply_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    """辞書で渡された条件でDataFrameを絞り込む。値が空・Noneの条件は無視する。"""
    if df.empty:
        return df

    result = df.copy()

    free_word = filters.get("free_word")
    if free_word:
        mask = (
            result["title"].fillna("").str.contains(free_word, case=False, na=False)
            | result["body"].fillna("").str.contains(free_word, case=False, na=False)
            | result["description"].fillna("").str.contains(free_word, case=False, na=False)
        )
        result = result[mask]

    keyword = filters.get("matched_keyword")
    if keyword:
        result = result[result["matched_keyword"].fillna("") == keyword]

    excluded_only = filters.get("excluded_only")
    if excluded_only is True:
        result = result[result["excluded_keyword"].fillna("") != ""]
    elif excluded_only is False:
        result = result[result["excluded_keyword"].fillna("") == ""]

    min_budget = filters.get("min_budget")
    if min_budget:
        result = result[result["budget_max"].fillna(0) >= min_budget]

    max_budget = filters.get("max_budget")
    if max_budget:
        result = result[result["budget_min"].fillna(0) <= max_budget]

    job_type = filters.get("job_type")
    if job_type:
        result = result[result["job_type"] == job_type]

    category = filters.get("category")
    if category:
        result = result[result["category"] == category]

    published_from = filters.get("published_from")
    if published_from:
        result = result[result["published_at"].fillna("") >= published_from]

    deadline_to = filters.get("deadline_to")
    if deadline_to:
        result = result[
            (result["deadline"].fillna("") != "") & (result["deadline"] <= deadline_to)
        ]

    max_applicants = filters.get("max_applicants")
    if max_applicants is not None:
        result = result[result["applicant_count"].fillna(10**9) <= max_applicants]

    min_client_rating = filters.get("min_client_rating")
    if min_client_rating:
        result = result[result["client_rating"].fillna(0) >= min_client_rating]

    identity_verified = filters.get("identity_verified")
    if identity_verified is True:
        result = result[result["identity_verified"] == 1]
    elif identity_verified is False:
        result = result[result["identity_verified"] != 1]

    status = filters.get("status")
    if status:
        result = result[result["status"].isin(status if isinstance(status, list) else [status])]

    is_favorite = filters.get("is_favorite")
    if is_favorite:
        result = result[result["is_favorite"] == 1]

    source_type = filters.get("source_type")
    if source_type:
        result = result[result["source_type"] == source_type]

    return result


def apply_sort(df: pd.DataFrame, sort_label: str, options: dict | None = None) -> pd.DataFrame:
    """SORT_OPTIONS（またはoptionsで指定された辞書）の基準で並べ替える。NULLは常に末尾。"""
    options = options or SORT_OPTIONS
    if df.empty or sort_label not in options:
        return df
    column, ascending = options[sort_label]
    if column not in df.columns:
        return df
    return df.sort_values(
        by=column, ascending=ascending, na_position="last", kind="stable"
    )


def apply_analysis_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    """分析結果一覧ページ用の絞り込み（総合スコア・AI適合度・安全度・優先度等）。"""
    if df.empty:
        return df

    result = df.copy()

    min_total_score = filters.get("min_total_score")
    if min_total_score:
        result = result[result["total_score"].fillna(-1) >= min_total_score]

    min_ai_score = filters.get("min_ai_score")
    if min_ai_score:
        result = result[result["ai_suitability_score"].fillna(-1) >= min_ai_score]

    min_safety_score = filters.get("min_safety_score")
    if min_safety_score:
        result = result[result["safety_score"].fillna(-1) >= min_safety_score]

    priority = filters.get("application_priority")
    if priority:
        result = result[result["application_priority"].isin(priority if isinstance(priority, list) else [priority])]

    recommendation = filters.get("recommendation")
    if recommendation:
        result = result[result["recommendation"].isin(recommendation if isinstance(recommendation, list) else [recommendation])]

    difficulty = filters.get("difficulty")
    if difficulty:
        result = result[result["difficulty"].isin(difficulty if isinstance(difficulty, list) else [difficulty])]

    risk_level = filters.get("risk_level")
    if risk_level:
        result = result[result["risk_level"].isin(risk_level if isinstance(risk_level, list) else [risk_level])]

    budget_evaluation = filters.get("budget_evaluation")
    if budget_evaluation:
        result = result[result["budget_evaluation"].isin(budget_evaluation if isinstance(budget_evaluation, list) else [budget_evaluation])]

    analyzed_state = filters.get("analyzed_state")
    if analyzed_state == "分析済みのみ":
        result = result[result["analysis_id"].notna()]
    elif analyzed_state == "未分析のみ":
        result = result[result["analysis_id"].isna()]

    analyzed_date = filters.get("analyzed_date")
    if analyzed_date:
        result = result[result["analyzed_at"].fillna("").str.startswith(analyzed_date)]

    skill_keyword = filters.get("skill_keyword")
    if skill_keyword:
        def _contains_skill(cell) -> bool:
            if not isinstance(cell, list):
                return False
            return any(skill_keyword.lower() in str(s).lower() for s in cell)

        skill_field = filters.get("skill_field", "required_skills")
        if skill_field in result.columns:
            result = result[result[skill_field].apply(_contains_skill)]

    return result
