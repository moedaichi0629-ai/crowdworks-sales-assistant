"""期間指定・期間比較(period_service)のテスト。"""
from __future__ import annotations

import datetime

from src.analytics.period_service import (
    PERIOD_ALL,
    PERIOD_CUSTOM,
    PERIOD_LAST_MONTH,
    PERIOD_LAST_WEEK,
    PERIOD_THIS_MONTH,
    PERIOD_THIS_WEEK,
    PERIOD_TODAY,
    previous_period,
    resolve_period,
    today_jst,
)
from src.utils import now_jst


def test_today_period():
    d_from, d_to = resolve_period(PERIOD_TODAY)
    assert d_from == d_to == today_jst().isoformat()


def test_this_week_includes_today():
    d_from, d_to = resolve_period(PERIOD_THIS_WEEK)
    today = today_jst().isoformat()
    assert d_from <= today <= d_to


def test_this_month_starts_on_first_day():
    d_from, _ = resolve_period(PERIOD_THIS_MONTH)
    assert d_from.endswith("-01")


def test_custom_period_uses_given_dates():
    d_from, d_to = resolve_period(PERIOD_CUSTOM, "2026-01-01", "2026-01-31")
    assert (d_from, d_to) == ("2026-01-01", "2026-01-31")


def test_all_period_is_wide_range():
    d_from, d_to = resolve_period(PERIOD_ALL)
    assert d_from < "2000-01-01"
    assert d_to > "2100-01-01"


def test_previous_period_same_length():
    d_from, d_to = "2026-07-08", "2026-07-14"  # 7日間
    prev_from, prev_to = previous_period(d_from, d_to)
    assert prev_to == "2026-07-07"
    assert prev_from == "2026-07-01"
    prev_length = (datetime.date.fromisoformat(prev_to) - datetime.date.fromisoformat(prev_from)).days + 1
    assert prev_length == 7


def test_last_week_and_last_month_precede_this_period():
    this_week = resolve_period(PERIOD_THIS_WEEK)
    last_week = resolve_period(PERIOD_LAST_WEEK)
    assert last_week[1] < this_week[0]

    this_month = resolve_period(PERIOD_THIS_MONTH)
    last_month = resolve_period(PERIOD_LAST_MONTH)
    assert last_month[1] < this_month[0]


def test_today_jst_matches_utils_now_jst_date():
    assert today_jst() == now_jst().date()
