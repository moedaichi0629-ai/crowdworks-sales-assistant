"""応募タイミング（曜日・時間帯・掲載からの経過時間）の傾向分析。因果関係は断定しない。"""
from __future__ import annotations

import datetime

from src.analytics.kpi_service import rate
from src.config import RESULT_TYPE_HIRED

WEEKDAY_LABELS_JA = ["月", "火", "水", "木", "金", "土", "日"]

HOUR_BANDS = [
    ("0〜5時", 0, 5), ("6〜8時", 6, 8), ("9〜11時", 9, 11), ("12〜14時", 12, 14),
    ("15〜17時", 15, 17), ("18〜20時", 18, 20), ("21〜23時", 21, 23),
]


def _parse_dt(text: str | None) -> datetime.datetime | None:
    if not text:
        return None
    try:
        return datetime.datetime.strptime(str(text)[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _hour_band(hour: int) -> str:
    for label, low, high in HOUR_BANDS:
        if low <= hour <= high:
            return label
    return HOUR_BANDS[-1][0]


def _summarize(items: list[dict]) -> dict:
    total = len(items)
    responded = [r for r in items if (r.get("response_count") or 0) > 0]
    hired = [r for r in items if r.get("result_type") == RESULT_TYPE_HIRED]
    return {
        "application_count": total,
        "response_rate": rate(len(responded), total),
        "hired_rate": rate(len(hired), total),
    }


def analyze_by_weekday(records: list[dict]) -> dict:
    """曜日別の応募数・返信率・採用率を集計する。"""
    buckets: dict[str, list[dict]] = {label: [] for label in WEEKDAY_LABELS_JA}
    for r in records:
        dt = _parse_dt(r.get("applied_at"))
        if dt:
            buckets[WEEKDAY_LABELS_JA[dt.weekday()]].append(r)
    return {label: _summarize(items) for label, items in buckets.items()}


def analyze_by_hour(records: list[dict]) -> dict:
    """時間帯別の応募数・返信率を集計する。"""
    buckets: dict[str, list[dict]] = {label: [] for label, _, _ in HOUR_BANDS}
    for r in records:
        dt = _parse_dt(r.get("applied_at"))
        if dt:
            buckets[_hour_band(dt.hour)].append(r)
    return {label: _summarize(items) for label, items in buckets.items()}


def analyze_by_freshness(records: list[dict]) -> dict:
    """掲載から応募までの経過時間帯ごとの成果を集計する（傾向の把握のみ。因果関係は断定しない）。"""
    buckets = {"24時間以内": [], "48時間以内": [], "72時間以降": []}
    for r in records:
        published = _parse_dt((r.get("job_snapshot") or {}).get("published_at"))
        applied = _parse_dt(r.get("applied_at"))
        if not published or not applied:
            continue
        hours = (applied - published).total_seconds() / 3600
        if hours < 0:
            continue
        if hours <= 24:
            buckets["24時間以内"].append(r)
        elif hours <= 48:
            buckets["48時間以内"].append(r)
        else:
            buckets["72時間以降"].append(r)
    return {label: _summarize(items) for label, items in buckets.items()}
