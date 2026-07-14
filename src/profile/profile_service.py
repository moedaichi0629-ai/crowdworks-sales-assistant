"""スキルプロフィール管理のサービス層（画面から呼び出すCRUDラッパー）。"""
from __future__ import annotations

import sqlite3

from src.repositories import (
    add_portfolio,
    add_skill,
    delete_portfolio,
    delete_skill,
    get_profile,
    get_profile_bundle,
    list_portfolios,
    list_skills,
    update_portfolio,
    update_profile,
    update_skill,
)
from src.logger import get_logger

logger = get_logger()


def get_or_create_default_profile(conn: sqlite3.Connection) -> dict:
    """デフォルトプロフィールを取得する。存在しない場合はマイグレーションで作成されているはず。"""
    profile = get_profile(conn, "default")
    if profile is None:
        raise ValueError("デフォルトプロフィールが見つかりません。データベースの初期化を確認してください。")
    return profile


def get_full_profile(conn: sqlite3.Connection) -> dict:
    bundle = get_profile_bundle(conn, "default")
    if bundle is None:
        raise ValueError("デフォルトプロフィールが見つかりません。")
    return bundle


def save_basic_info(conn: sqlite3.Connection, profile_id: int, data: dict) -> None:
    update_profile(conn, profile_id, data)
    logger.info("プロフィール基本情報を更新しました: profile_id=%s", profile_id)


def add_profile_skill(conn: sqlite3.Connection, profile_id: int, data: dict) -> int:
    return add_skill(conn, profile_id, data)


def edit_profile_skill(conn: sqlite3.Connection, skill_id: int, data: dict) -> None:
    update_skill(conn, skill_id, data)


def remove_profile_skill(conn: sqlite3.Connection, skill_id: int) -> None:
    delete_skill(conn, skill_id)


def add_profile_portfolio(conn: sqlite3.Connection, profile_id: int, data: dict) -> int:
    return add_portfolio(conn, profile_id, data)


def edit_profile_portfolio(conn: sqlite3.Connection, portfolio_id: int, data: dict) -> None:
    update_portfolio(conn, portfolio_id, data)


def remove_profile_portfolio(conn: sqlite3.Connection, portfolio_id: int) -> None:
    delete_portfolio(conn, portfolio_id)
