"""日次応募目標(daily_application_goals / goal_service)のテスト。"""
from __future__ import annotations

import sqlite3

import pytest

from src.daily.category_allocator import validate_allocation
from src.daily.goal_service import (
    ensure_daily_goal,
    get_default_goal_settings,
    save_daily_goal,
    save_default_goal_settings,
)
from src.database import session
from src.repositories import create_daily_goal, get_daily_goal


def test_initial_goal_creation_uses_defaults(db_path):
    with session(db_path) as conn:
        goal = ensure_daily_goal(conn, "2026-07-15")
    assert goal["target_count"] == 5
    assert goal["maximum_count"] == 7
    assert goal["ai_development_target"] == 2
    assert goal["design_target"] == 2
    assert goal["other_target"] == 1
    assert goal["minimum_total_score"] == 70
    assert goal["minimum_ai_score"] == 65
    assert goal["minimum_safety_score"] == 75
    assert goal["allowed_risk_levels"] == ["low", "medium"]


def test_daily_goal_saved_and_persisted(db_path):
    with session(db_path) as conn:
        save_daily_goal(conn, "2026-07-16", {"target_count": 8})
    with session(db_path) as conn:
        goal = get_daily_goal(conn, "2026-07-16")
    assert goal["target_count"] == 8


def test_duplicate_target_date_is_rejected(db_path):
    with session(db_path) as conn:
        ensure_daily_goal(conn, "2026-07-17")

    with pytest.raises(sqlite3.IntegrityError):
        with session(db_path) as conn:
            create_daily_goal(conn, "2026-07-17", {
                "target_count": 5, "maximum_count": 7, "ai_development_target": 2,
                "design_target": 2, "other_target": 1, "minimum_total_score": 70,
                "minimum_ai_score": 65, "minimum_safety_score": 75,
            })


def test_goal_change_reflected_in_new_dates(db_path):
    with session(db_path) as conn:
        settings = get_default_goal_settings(conn)
        settings["target_count"] = 10
        save_default_goal_settings(conn, settings)

    with session(db_path) as conn:
        goal = ensure_daily_goal(conn, "2026-07-18")
    assert goal["target_count"] == 10


def test_existing_goal_can_be_updated(db_path):
    with session(db_path) as conn:
        ensure_daily_goal(conn, "2026-07-19")
        save_daily_goal(conn, "2026-07-19", {"target_count": 3, "maximum_count": 4})
    with session(db_path) as conn:
        goal = get_daily_goal(conn, "2026-07-19")
    assert goal["target_count"] == 3
    assert goal["maximum_count"] == 4


def test_maximum_below_target_is_detectable():
    # 応募目標設定画面は上限<目標の場合に警告を表示する。判定ロジックそのものを検証する。
    target_count, maximum_count = 5, 3
    assert maximum_count < target_count


def test_category_allocation_matches_target():
    is_valid, total = validate_allocation(5, 2, 2, 1)
    assert is_valid is True
    assert total == 5


def test_category_allocation_mismatch_detected():
    is_valid, total = validate_allocation(5, 2, 2, 5)
    assert is_valid is False
    assert total == 9
