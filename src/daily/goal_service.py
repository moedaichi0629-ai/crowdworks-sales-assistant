"""1日あたりの応募目標(daily_application_goals)の取得・作成・更新を行うサービス層。

daily_selection_settings に保存された既定値（応募目標設定画面で編集）をもとに、
まだ存在しない日付の目標行を自動作成する（要件11: 日付変更時に新しい日次データを自動作成する）。
"""
from __future__ import annotations

import sqlite3

from src.config import DEFAULT_DAILY_GOAL_SETTINGS, DEFAULT_DAILY_SCORE_WEIGHTS
from src.logger import get_logger
from src.repositories import (
    create_daily_goal,
    get_all_daily_selection_settings,
    get_daily_goal,
    list_daily_goals,
    save_daily_selection_setting,
    update_daily_goal,
)
from src.utils import now_jst

logger = get_logger()

_GOAL_PREFIX = "goal_default."
_WEIGHT_PREFIX = "score_weight."


def today_jst_str() -> str:
    """日本時間の「今日」を YYYY-MM-DD 形式で返す（1日の区切りは日本時間0:00〜23:59）。"""
    return now_jst().strftime("%Y-%m-%d")


def get_default_goal_settings(conn: sqlite3.Connection) -> dict:
    """新しい日付の目標を作成する際に使う既定値（応募目標設定画面から変更可能）を取得する。"""
    stored = get_all_daily_selection_settings(conn)
    settings = dict(DEFAULT_DAILY_GOAL_SETTINGS)
    for key, value in stored.items():
        if key.startswith(_GOAL_PREFIX):
            settings[key[len(_GOAL_PREFIX):]] = value
    return settings


def save_default_goal_settings(conn: sqlite3.Connection, settings: dict) -> None:
    for key, value in settings.items():
        save_daily_selection_setting(conn, f"{_GOAL_PREFIX}{key}", value)
    logger.info("日次目標更新: 既定の応募目標設定を更新しました。")


def get_score_weights(conn: sqlite3.Connection) -> dict:
    stored = get_all_daily_selection_settings(conn)
    weights = dict(DEFAULT_DAILY_SCORE_WEIGHTS)
    for key, value in stored.items():
        if key.startswith(_WEIGHT_PREFIX):
            weights[key[len(_WEIGHT_PREFIX):]] = value
    return weights


def save_score_weights(conn: sqlite3.Connection, weights: dict) -> None:
    for key, value in weights.items():
        save_daily_selection_setting(conn, f"{_WEIGHT_PREFIX}{key}", value)
    logger.info("日次目標更新: デイリー優先スコアの重みを更新しました。")


def ensure_daily_goal(conn: sqlite3.Connection, target_date: str) -> dict:
    """指定日の応募目標を取得する。存在しなければ既定値から新規作成する（重複しない）。"""
    goal = get_daily_goal(conn, target_date)
    if goal is not None:
        return goal

    defaults = get_default_goal_settings(conn)
    weights = get_score_weights(conn)
    data = {**defaults, "score_weights": weights}
    create_daily_goal(conn, target_date, data)
    logger.info("日次目標作成: target_date=%s", target_date)
    return get_daily_goal(conn, target_date)


def save_daily_goal(conn: sqlite3.Connection, target_date: str, data: dict) -> dict:
    """指定日の応募目標を更新する（存在しなければ既定値から作成してから更新する）。"""
    ensure_daily_goal(conn, target_date)
    update_daily_goal(conn, target_date, data)
    logger.info("日次目標更新: target_date=%s", target_date)
    return get_daily_goal(conn, target_date)


def get_goal_history(conn: sqlite3.Connection, limit: int = 60) -> list[dict]:
    return list_daily_goals(conn, limit)
