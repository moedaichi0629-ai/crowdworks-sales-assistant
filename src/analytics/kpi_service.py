"""営業成績の基本KPI集計。

返信数・面談数は、原則として応募単位のユニーク件数で数える
（同一応募に複数の返信・面談があっても1件として数える）。
分母が0の場合、率はNone（画面側では「-」や非表示にする）。
"""
from __future__ import annotations

import datetime
import sqlite3

from src.analytics.period_service import filter_by_date_range
from src.config import APP_STATUS_UNKNOWN, RESULT_TYPE_HIRED, RESULT_TYPE_REJECTED, RESULT_TYPE_WITHDRAWN
from src.repositories import (
    count_candidates_in_range,
    count_drafts_created_in_range,
    count_drafts_ready_in_range,
    count_jobs_analyzed_in_range,
    count_jobs_collected_in_range,
    list_application_analytics_base,
)


def _hours_between(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    try:
        s = datetime.datetime.strptime(str(start)[:19], "%Y-%m-%d %H:%M:%S")
        e = datetime.datetime.strptime(str(end)[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return (e - s).total_seconds() / 3600


def _days_between(start: str | None, end: str | None) -> float | None:
    hours = _hours_between(start, end)
    return hours / 24 if hours is not None else None


def rate(numerator: int, denominator: int) -> float | None:
    """パーセント表記の率を返す。分母が0の場合はNone（0%表示ではなく非表示にできるように）。"""
    if not denominator:
        return None
    return round(numerator / denominator * 100, 1)


def get_base_records(conn: sqlite3.Connection, date_from: str, date_to: str) -> list[dict]:
    """指定期間(応募日基準)の応募履歴データを返す。"""
    all_records = list_application_analytics_base(conn)
    return filter_by_date_range(all_records, "applied_at", date_from, date_to)


def compute_kpis_from_records(records: list[dict]) -> dict:
    """応募履歴データ(list_application_analytics_base形式)からKPIを計算する。"""
    total = len(records)
    responded = [r for r in records if (r.get("response_count") or 0) > 0]
    interviewed = [r for r in records if (r.get("interview_count") or 0) > 0]
    hired = [r for r in records if r.get("result_type") == RESULT_TYPE_HIRED]
    contracted = [r for r in hired if r.get("contract_amount") is not None]
    rejected = [r for r in records if r.get("result_type") == RESULT_TYPE_REJECTED]
    withdrawn = [r for r in records if r.get("result_type") == RESULT_TYPE_WITHDRAWN]
    unknown = [r for r in records if r.get("application_status") == APP_STATUS_UNKNOWN]

    contract_amounts = [r["contract_amount"] for r in contracted if r.get("contract_amount") is not None]

    response_hours: list[float] = []
    for r in responded:
        h = _hours_between(r.get("applied_at"), r.get("first_response_at"))
        if h is not None:
            response_hours.append(h)

    hire_days: list[float] = []
    for r in hired:
        d = _days_between(r.get("applied_at"), r.get("hired_at") or r.get("result_date"))
        if d is not None:
            hire_days.append(d)

    return {
        "application_count": total,
        "response_count": len(responded),
        "response_rate": rate(len(responded), total),
        "interview_count": len(interviewed),
        "interview_rate": rate(len(interviewed), total),
        "hired_count": len(hired),
        "hired_rate": rate(len(hired), total),
        "contracted_count": len(contracted),
        "contracted_rate": rate(len(contracted), total),
        "rejected_count": len(rejected),
        "withdrawn_count": len(withdrawn),
        "unknown_count": len(unknown),
        "contract_amount_total": sum(contract_amounts) if contract_amounts else None,
        "contract_amount_avg": round(sum(contract_amounts) / len(contract_amounts)) if contract_amounts else None,
        "contract_amount_max": max(contract_amounts) if contract_amounts else None,
        "contract_amount_min": min(contract_amounts) if contract_amounts else None,
        "avg_hours_to_response": round(sum(response_hours) / len(response_hours), 1) if response_hours else None,
        "avg_days_to_hire": round(sum(hire_days) / len(hire_days), 1) if hire_days else None,
    }


def build_daily_trend(records: list[dict]) -> list[dict]:
    """日別の応募数・返信数・採用数・契約金額を集計する（ダッシュボードのグラフ表示用）。"""
    by_date: dict[str, dict] = {}
    for r in records:
        applied_date = str(r.get("applied_at") or "")[:10]
        if not applied_date:
            continue
        bucket = by_date.setdefault(applied_date, {"date": applied_date, "応募数": 0, "返信数": 0, "採用数": 0, "契約金額": 0})
        bucket["応募数"] += 1
        if (r.get("response_count") or 0) > 0:
            bucket["返信数"] += 1
        if r.get("result_type") == RESULT_TYPE_HIRED:
            bucket["採用数"] += 1
            if r.get("contract_amount") is not None:
                bucket["契約金額"] += r["contract_amount"]
    return [by_date[d] for d in sorted(by_date)]


def compute_kpis(conn: sqlite3.Connection, date_from: str, date_to: str) -> dict:
    """指定期間のKPIを算出する（案件収集〜契約金額まで、応募パイプライン全体）。"""
    records = get_base_records(conn, date_from, date_to)
    kpis = compute_kpis_from_records(records)
    kpis["collected_count"] = count_jobs_collected_in_range(conn, date_from, date_to)
    kpis["analyzed_count"] = count_jobs_analyzed_in_range(conn, date_from, date_to)
    kpis["candidate_count"] = count_candidates_in_range(conn, date_from, date_to)
    kpis["draft_count"] = count_drafts_created_in_range(conn, date_from, date_to)
    kpis["ready_count"] = count_drafts_ready_in_range(conn, date_from, date_to)
    kpis["date_from"] = date_from
    kpis["date_to"] = date_to
    return kpis
