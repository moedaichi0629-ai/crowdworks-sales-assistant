"""ポートフォリオ自動選択のサービス層（案件ごとの関連度計算・選択状態の保存/取得）。"""
from __future__ import annotations

import sqlite3

from src.logger import get_logger
from src.portfolio.portfolio_matcher import select_portfolios
from src.repositories import (
    add_portfolio,
    delete_portfolio,
    get_portfolio_matches_for_job,
    get_portfolios_by_ids,
    get_selected_portfolio_matches,
    list_portfolios,
    save_portfolio_matches,
    update_portfolio,
    update_portfolio_match_selection,
)

logger = get_logger()


def compute_and_save_portfolio_matches(
    conn: sqlite3.Connection, job: dict, profile_id: int, max_selections: int = 3,
) -> list[dict]:
    """案件に対する全ポートフォリオの関連度を計算し、上位を自動選択して保存する。"""
    portfolios = list_portfolios(conn, profile_id)
    matches = select_portfolios(job, portfolios, max_selections=max_selections)
    save_portfolio_matches(conn, job["id"], matches)
    logger.info("ポートフォリオ自動選択を実行しました: job_id=%s", job["id"])
    return matches


def get_selected_portfolios_with_detail(conn: sqlite3.Connection, job_id: int) -> list[dict]:
    """案件で選択済みのポートフォリオを、詳細情報（URL等）付きで表示順に取得する。"""
    selected = get_selected_portfolio_matches(conn, job_id)
    if not selected:
        return []
    portfolio_map = {p["id"]: p for p in get_portfolios_by_ids(conn, [m["portfolio_id"] for m in selected])}
    result = []
    for m in selected:
        portfolio = portfolio_map.get(m["portfolio_id"])
        if portfolio is None:
            continue
        result.append({**portfolio, "relevance_score": m["relevance_score"], "match_reason": m["match_reason"]})
    return result


def update_manual_portfolio_selection(conn: sqlite3.Connection, job_id: int, selected_ids: list[int]) -> None:
    """ユーザーによる手動追加・削除・並べ替えを反映する。"""
    update_portfolio_match_selection(conn, job_id, selected_ids)
    logger.info("ポートフォリオ選択を手動変更しました: job_id=%s selected=%s", job_id, selected_ids)


def list_portfolio_matches(conn: sqlite3.Connection, job_id: int) -> list[dict]:
    return get_portfolio_matches_for_job(conn, job_id)
