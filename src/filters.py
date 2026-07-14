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


def apply_sort(df: pd.DataFrame, sort_label: str) -> pd.DataFrame:
    """SORT_OPTIONSで指定された基準で並べ替える。NULLは常に末尾。"""
    if df.empty or sort_label not in SORT_OPTIONS:
        return df
    column, ascending = SORT_OPTIONS[sort_label]
    return df.sort_values(
        by=column, ascending=ascending, na_position="last", kind="stable"
    )
