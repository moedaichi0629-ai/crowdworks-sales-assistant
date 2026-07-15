"""期間指定・期間比較のための共通ユーティリティ。日本時間の「今日」を基準に日付を扱う。"""
from __future__ import annotations

import datetime

from src.utils import now_jst

PERIOD_TODAY = "今日"
PERIOD_YESTERDAY = "昨日"
PERIOD_THIS_WEEK = "今週"
PERIOD_LAST_WEEK = "先週"
PERIOD_THIS_MONTH = "今月"
PERIOD_LAST_MONTH = "先月"
PERIOD_LAST_7_DAYS = "過去7日"
PERIOD_LAST_30_DAYS = "過去30日"
PERIOD_LAST_90_DAYS = "過去90日"
PERIOD_ALL = "全期間"
PERIOD_CUSTOM = "任意期間"

PERIOD_OPTIONS = [
    PERIOD_TODAY, PERIOD_YESTERDAY, PERIOD_THIS_WEEK, PERIOD_LAST_WEEK, PERIOD_THIS_MONTH,
    PERIOD_LAST_MONTH, PERIOD_LAST_7_DAYS, PERIOD_LAST_30_DAYS, PERIOD_LAST_90_DAYS,
    PERIOD_ALL, PERIOD_CUSTOM,
]

_MIN_DATE = "0001-01-01"
_MAX_DATE = "9999-12-31"


def today_jst() -> datetime.date:
    return now_jst().date()


def resolve_period(period: str, custom_from: str | None = None, custom_to: str | None = None) -> tuple[str, str]:
    """期間名から (開始日, 終了日) を YYYY-MM-DD 形式（日本時間・両端含む）で返す。"""
    today = today_jst()

    if period == PERIOD_TODAY:
        return today.isoformat(), today.isoformat()
    if period == PERIOD_YESTERDAY:
        d = today - datetime.timedelta(days=1)
        return d.isoformat(), d.isoformat()
    if period == PERIOD_THIS_WEEK:
        start = today - datetime.timedelta(days=today.weekday())
        return start.isoformat(), today.isoformat()
    if period == PERIOD_LAST_WEEK:
        this_week_start = today - datetime.timedelta(days=today.weekday())
        start = this_week_start - datetime.timedelta(days=7)
        end = this_week_start - datetime.timedelta(days=1)
        return start.isoformat(), end.isoformat()
    if period == PERIOD_THIS_MONTH:
        start = today.replace(day=1)
        return start.isoformat(), today.isoformat()
    if period == PERIOD_LAST_MONTH:
        first_this_month = today.replace(day=1)
        last_month_end = first_this_month - datetime.timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        return last_month_start.isoformat(), last_month_end.isoformat()
    if period == PERIOD_LAST_7_DAYS:
        start = today - datetime.timedelta(days=6)
        return start.isoformat(), today.isoformat()
    if period == PERIOD_LAST_30_DAYS:
        start = today - datetime.timedelta(days=29)
        return start.isoformat(), today.isoformat()
    if period == PERIOD_LAST_90_DAYS:
        start = today - datetime.timedelta(days=89)
        return start.isoformat(), today.isoformat()
    if period == PERIOD_ALL:
        return _MIN_DATE, _MAX_DATE
    if period == PERIOD_CUSTOM:
        return (custom_from or today.isoformat()), (custom_to or today.isoformat())
    return today.isoformat(), today.isoformat()


def previous_period(date_from: str, date_to: str) -> tuple[str, str]:
    """指定期間と同じ日数だけ遡った、直前の期間を返す（期間比較用）。

    「今週と先週」「今月と先月」「過去30日とその前30日」のいずれも、
    "同じ長さの直前の期間" として一貫した方法で計算する。
    """
    d_from = datetime.date.fromisoformat(date_from)
    d_to = datetime.date.fromisoformat(date_to)
    length = (d_to - d_from).days + 1
    prev_to = d_from - datetime.timedelta(days=1)
    prev_from = prev_to - datetime.timedelta(days=length - 1)
    return prev_from.isoformat(), prev_to.isoformat()


def filter_by_date_range(records: list[dict], date_field: str, date_from: str, date_to: str) -> list[dict]:
    """recordsを date_field（YYYY-MM-DD... 形式の文字列）の日付部分で絞り込む。"""
    return [
        r for r in records
        if r.get(date_field) and date_from <= str(r[date_field])[:10] <= date_to
    ]
