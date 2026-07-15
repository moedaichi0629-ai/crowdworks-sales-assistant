"""1日あたりの応募上限管理。

応募を計画的に行うための管理値であり、クラウドワークスへの応募操作を直接制御するものではない
（自動送信・自動応募は一切行わない）。
"""
from __future__ import annotations

import sqlite3

from src.daily.goal_service import ensure_daily_goal
from src.logger import get_logger
from src.repositories import count_applications_for_date

logger = get_logger()


def get_limit_status(conn: sqlite3.Connection, target_date: str) -> dict:
    """本日の応募目標・上限に対する現在の状況を返す。"""
    goal = ensure_daily_goal(conn, target_date)
    applied_count = count_applications_for_date(conn, target_date)
    target_count = int(goal.get("target_count", 0) or 0)
    maximum_count = int(goal.get("maximum_count", 0) or 0)
    return {
        "applied_count": applied_count,
        "target_count": target_count,
        "maximum_count": maximum_count,
        "goal_achieved": target_count > 0 and applied_count >= target_count,
        "limit_reached": maximum_count > 0 and applied_count >= maximum_count,
        "requires_reason": maximum_count > 0 and applied_count >= maximum_count,
    }


def log_limit_event(target_date: str, applied_count: int, maximum_count: int, over_limit: bool) -> None:
    """応募上限到達・超過をログへ記録する（営業文全文・個人情報は記録しない）。"""
    if over_limit:
        logger.warning(
            "応募上限超過: target_date=%s 応募数=%s 上限=%s", target_date, applied_count, maximum_count,
        )
    elif maximum_count and applied_count >= maximum_count:
        logger.info(
            "応募上限到達: target_date=%s 応募数=%s 上限=%s", target_date, applied_count, maximum_count,
        )
