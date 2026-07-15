"""応募上限管理(application_limit_service / application_record_service)のテスト。"""
from __future__ import annotations

import pytest

from src.applications.application_limit_service import get_limit_status
from src.applications.application_record_service import OverLimitReasonRequiredError, record_application
from src.daily.goal_service import save_daily_goal
from src.database import session
from src.repositories import count_applications_for_date, create_application_record, insert_job

TARGET_DATE = "2026-07-15"


def _insert_job(db_path, title="テスト案件"):
    with session(db_path) as conn:
        return insert_job(conn, {"title": title, "source_type": "manual"})


def test_limit_status_below_target(db_path):
    with session(db_path) as conn:
        save_daily_goal(conn, TARGET_DATE, {"target_count": 3, "maximum_count": 5})
        status = get_limit_status(conn, TARGET_DATE)
    assert status["goal_achieved"] is False
    assert status["limit_reached"] is False


def test_limit_status_goal_achieved(db_path):
    with session(db_path) as conn:
        save_daily_goal(conn, TARGET_DATE, {"target_count": 1, "maximum_count": 5})
    job_id = _insert_job(db_path)
    with session(db_path) as conn:
        record_application(conn, TARGET_DATE, job_id, None, 10000, 5)
        status = get_limit_status(conn, TARGET_DATE)
    assert status["goal_achieved"] is True
    assert status["limit_reached"] is False


def test_limit_reached_requires_reason(db_path):
    with session(db_path) as conn:
        save_daily_goal(conn, TARGET_DATE, {"target_count": 1, "maximum_count": 1})
    job_id = _insert_job(db_path)
    with session(db_path) as conn:
        record_application(conn, TARGET_DATE, job_id, None, 10000, 5)
        status = get_limit_status(conn, TARGET_DATE)
    assert status["limit_reached"] is True

    job_id2 = _insert_job(db_path, "2件目案件")
    with session(db_path) as conn:
        with pytest.raises(OverLimitReasonRequiredError):
            record_application(conn, TARGET_DATE, job_id2, None, 10000, 5)


def test_over_limit_recorded_with_reason(db_path):
    with session(db_path) as conn:
        save_daily_goal(conn, TARGET_DATE, {"target_count": 1, "maximum_count": 1})
    job_id = _insert_job(db_path)
    with session(db_path) as conn:
        record_application(conn, TARGET_DATE, job_id, None, 10000, 5)

    job_id2 = _insert_job(db_path, "2件目案件")
    with session(db_path) as conn:
        record_application(
            conn, TARGET_DATE, job_id2, None, 10000, 5, over_limit_reason="急ぎの高単価案件のため",
        )

    with session(db_path) as conn:
        records = conn.execute("SELECT * FROM application_records WHERE job_id = ?", (job_id2,)).fetchall()
    assert records[0]["is_over_limit"] == 1
    assert records[0]["over_limit_reason"] == "急ぎの高単価案件のため"


def test_application_count_resets_for_new_date(db_path):
    """応募日時(applied_at)をもとに集計するため、日付が変わればその日の応募数は0から始まる。"""
    job_id = _insert_job(db_path)
    with session(db_path) as conn:
        save_daily_goal(conn, "2026-07-14", {"target_count": 1, "maximum_count": 1})
        save_daily_goal(conn, "2026-07-15", {"target_count": 1, "maximum_count": 1})
        create_application_record(conn, {
            "job_id": job_id, "applied_at": "2026-07-14 15:00:00", "proposed_price": 10000,
        })
        status_yesterday = get_limit_status(conn, "2026-07-14")
        status_today = get_limit_status(conn, "2026-07-15")
    assert status_yesterday["applied_count"] == 1
    assert status_today["applied_count"] == 0


def test_application_count_aggregated_by_applied_date_jst(db_path):
    job_id = _insert_job(db_path)
    with session(db_path) as conn:
        create_application_record(conn, {
            "job_id": job_id, "applied_at": "2026-07-15 23:59:59", "proposed_price": 10000,
        })
        create_application_record(conn, {
            "job_id": job_id, "applied_at": "2026-07-16 00:00:01", "proposed_price": 10000,
        })
        count_15 = count_applications_for_date(conn, "2026-07-15")
        count_16 = count_applications_for_date(conn, "2026-07-16")
    assert count_15 == 1
    assert count_16 == 1
