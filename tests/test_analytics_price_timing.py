"""金額帯・納期帯・曜日/時間帯別分析のテスト。"""
from __future__ import annotations

from src.analytics.kpi_service import get_base_records
from src.analytics.period_service import PERIOD_ALL, resolve_period
from src.analytics.price_analytics import analyze_by_delivery_band, analyze_by_price_band
from src.analytics.timing_analytics import analyze_by_freshness, analyze_by_hour, analyze_by_weekday
from src.crm.application_history_service import create_application_history
from src.database import session
from src.repositories import insert_job, save_job_analysis, update_application_record


def _job(db_path, title="案件", job_type="固定報酬制", published_at=None) -> int:
    with session(db_path) as conn:
        job_id = insert_job(conn, {
            "title": title, "body": "x" * 50, "job_type": job_type, "source_type": "manual",
            "published_at": published_at,
        })
        save_job_analysis(conn, job_id, {
            "rule_based_score": 70, "ai_suitability_score": 80, "total_score": 80,
            "safety_score": 90, "risk_level": "low", "used_ai": 0,
        })
        return job_id


def _records(db_path) -> list[dict]:
    with session(db_path) as conn:
        d_from, d_to = resolve_period(PERIOD_ALL)
        return get_base_records(conn, d_from, d_to)


def test_price_band_bucketing(db_path):
    j1, j2 = _job(db_path, "案件1"), _job(db_path, "案件2")
    with session(db_path) as conn:
        create_application_history(conn, j1, proposed_price=2000)
        create_application_history(conn, j2, proposed_price=40000)

    by_price = analyze_by_price_band(_records(db_path))
    assert by_price["固定報酬"]["〜3,000円"]["application_count"] == 1
    assert by_price["固定報酬"]["30,001〜50,000円"]["application_count"] == 1


def test_hourly_vs_fixed_split(db_path):
    j1 = _job(db_path, "時給案件", job_type="時間単価制")
    j2 = _job(db_path, "固定案件", job_type="固定報酬制")
    with session(db_path) as conn:
        create_application_history(conn, j1, proposed_price=1500)
        create_application_history(conn, j2, proposed_price=1500)

    by_price = analyze_by_price_band(_records(db_path))
    assert by_price["時間単価"]["〜3,000円"]["application_count"] == 1
    assert by_price["固定報酬"]["〜3,000円"]["application_count"] == 1


def test_delivery_band_bucketing(db_path):
    j1, j2 = _job(db_path, "案件1"), _job(db_path, "案件2")
    with session(db_path) as conn:
        create_application_history(conn, j1, proposed_delivery_days=2)
        create_application_history(conn, j2, proposed_delivery_days=20)

    by_delivery = analyze_by_delivery_band(_records(db_path))
    assert by_delivery["1〜3日"]["application_count"] == 1
    assert by_delivery["15〜30日"]["application_count"] == 1


def test_weekday_analysis(db_path):
    job = _job(db_path, "案件")
    with session(db_path) as conn:
        record_id = create_application_history(conn, job)
        update_application_record(conn, record_id, {"applied_at": "2026-07-15 10:00:00"})  # 水曜日

    by_weekday = analyze_by_weekday(_records(db_path))
    assert by_weekday["水"]["application_count"] == 1


def test_hour_band_analysis(db_path):
    job = _job(db_path, "案件")
    with session(db_path) as conn:
        record_id = create_application_history(conn, job)
        update_application_record(conn, record_id, {"applied_at": "2026-07-15 09:30:00"})

    by_hour = analyze_by_hour(_records(db_path))
    assert by_hour["9〜11時"]["application_count"] == 1


def test_freshness_within_24_hours(db_path):
    job = _job(db_path, "案件", published_at="2026-07-15 08:00:00")
    with session(db_path) as conn:
        record_id = create_application_history(conn, job)
        update_application_record(conn, record_id, {"applied_at": "2026-07-15 10:00:00"})  # 2時間後

    freshness = analyze_by_freshness(_records(db_path))
    assert freshness["24時間以内"]["application_count"] == 1


def test_freshness_after_72_hours(db_path):
    job = _job(db_path, "案件", published_at="2026-07-10 08:00:00")
    with session(db_path) as conn:
        record_id = create_application_history(conn, job)
        update_application_record(conn, record_id, {"applied_at": "2026-07-15 10:00:00"})  # 5日後

    freshness = analyze_by_freshness(_records(db_path))
    assert freshness["72時間以降"]["application_count"] == 1
