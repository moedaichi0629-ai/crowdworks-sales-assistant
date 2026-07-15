"""日次応募目標の達成状況分析。"""
from __future__ import annotations

import datetime
import sqlite3

from src.repositories import get_daily_application_counts, list_daily_goals


def analyze_goal_achievement(conn: sqlite3.Connection, date_from: str, date_to: str) -> dict:
    """指定期間の日次目標に対する達成状況を分析する。

    戻り値には、カレンダー/日別グラフ表示用の日別内訳(daily)も含む。
    """
    goals = [g for g in list_daily_goals(conn, limit=3650) if date_from <= g["target_date"] <= date_to]
    goals.sort(key=lambda g: g["target_date"])
    applied_counts = get_daily_application_counts(conn)

    daily: list[dict] = []
    achieved_days = 0
    over_limit_days = 0
    target_sum = 0
    applied_sum = 0
    current_streak = 0
    longest_streak = 0

    for goal in goals:
        target_date = goal["target_date"]
        target_count = int(goal.get("target_count", 0) or 0)
        maximum_count = int(goal.get("maximum_count", 0) or 0)
        applied_count = applied_counts.get(target_date, 0)

        achieved = target_count > 0 and applied_count >= target_count
        over_limit = maximum_count > 0 and applied_count > maximum_count

        if achieved:
            achieved_days += 1
            current_streak += 1
            longest_streak = max(longest_streak, current_streak)
        else:
            current_streak = 0

        if over_limit:
            over_limit_days += 1

        target_sum += target_count
        applied_sum += applied_count

        daily.append({
            "target_date": target_date, "target_count": target_count, "maximum_count": maximum_count,
            "applied_count": applied_count, "achieved": achieved, "over_limit": over_limit,
            "diff": applied_count - target_count,
        })

    goal_days = len(goals)
    return {
        "goal_days": goal_days,
        "achieved_days": achieved_days,
        "achievement_rate": round(achieved_days / goal_days * 100, 1) if goal_days else None,
        "avg_target_count": round(target_sum / goal_days, 1) if goal_days else None,
        "avg_applied_count": round(applied_sum / goal_days, 1) if goal_days else None,
        "avg_diff": round((applied_sum - target_sum) / goal_days, 1) if goal_days else None,
        "over_limit_days": over_limit_days,
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "daily": daily,
    }
