"""料金設定の読み書きと、応募金額提案のサービス層。"""
from __future__ import annotations

import sqlite3

from src.config import DEFAULT_PRICING_SETTINGS
from src.pricing.price_calculator import compute_price_suggestion
from src.repositories import get_all_pricing_settings, save_pricing_setting

_PREFIX = "pricing."


def get_pricing_settings(conn: sqlite3.Connection) -> dict:
    """画面から編集可能な料金設定を取得する（未保存の項目は既定値を使用）。"""
    stored = get_all_pricing_settings(conn)
    settings = dict(DEFAULT_PRICING_SETTINGS)
    for key, value in stored.items():
        if key.startswith(_PREFIX):
            settings[key[len(_PREFIX):]] = value
    return settings


def save_pricing_settings(conn: sqlite3.Connection, settings: dict) -> None:
    for key, value in settings.items():
        save_pricing_setting(conn, f"{_PREFIX}{key}", value)


def suggest_price(
    conn: sqlite3.Connection,
    job: dict,
    estimated_hours_min: int | None = None,
    estimated_hours_max: int | None = None,
    difficulty: str | None = None,
) -> dict:
    settings = get_pricing_settings(conn)
    return compute_price_suggestion(job, estimated_hours_min, estimated_hours_max, difficulty, settings)
