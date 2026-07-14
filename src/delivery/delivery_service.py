"""納期設定の読み書きと、納期提案のサービス層。"""
from __future__ import annotations

import sqlite3

from src.config import DEFAULT_DELIVERY_SETTINGS
from src.delivery.delivery_calculator import compute_delivery_suggestion
from src.repositories import get_all_pricing_settings, save_pricing_setting

_PREFIX = "delivery."


def get_delivery_settings(conn: sqlite3.Connection) -> dict:
    stored = get_all_pricing_settings(conn)
    settings = dict(DEFAULT_DELIVERY_SETTINGS)
    for key, value in stored.items():
        if key.startswith(_PREFIX):
            settings[key[len(_PREFIX):]] = value
    return settings


def save_delivery_settings(conn: sqlite3.Connection, settings: dict) -> None:
    for key, value in settings.items():
        save_pricing_setting(conn, f"{_PREFIX}{key}", value)


def suggest_delivery(
    conn: sqlite3.Connection,
    job: dict,
    estimated_hours_min: int | None = None,
    estimated_hours_max: int | None = None,
    estimated_days: int | None = None,
    difficulty: str | None = None,
    daily_available_hours: str | float | None = None,
    concurrent_job_count: int = 0,
) -> dict:
    settings = get_delivery_settings(conn)
    return compute_delivery_suggestion(
        job, estimated_hours_min, estimated_hours_max, estimated_days, difficulty,
        daily_available_hours, concurrent_job_count, settings,
    )
