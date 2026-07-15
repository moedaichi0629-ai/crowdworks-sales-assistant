"""KPI集計(kpi_service)のテスト。

返信数・面談数は応募単位のユニーク件数で数えるため、同一応募に複数の返信・面談があっても
1件として数えることを確認する。
"""
from __future__ import annotations

from src.analytics.kpi_service import compute_kpis
from src.analytics.period_service import PERIOD_ALL, resolve_period
from src.crm.application_history_service import create_application_history
from src.crm.interview_service import create_interview
from src.crm.response_service import record_response
from src.crm.result_service import record_hired, record_rejected
from src.database import session
from src.repositories import insert_job, save_job_analysis


def _job(db_path, title="テスト案件") -> int:
    with session(db_path) as conn:
        job_id = insert_job(conn, {"title": title, "body": "x" * 50, "source_type": "manual"})
        save_job_analysis(conn, job_id, {
            "rule_based_score": 70, "ai_suitability_score": 80, "total_score": 80,
            "safety_score": 90, "risk_level": "low", "used_ai": 0,
        })
        return job_id


def _kpis(db_path) -> dict:
    with session(db_path) as conn:
        d_from, d_to = resolve_period(PERIOD_ALL)
        return compute_kpis(conn, d_from, d_to)


def test_application_count(db_path):
    j1, j2 = _job(db_path, "A"), _job(db_path, "B")
    with session(db_path) as conn:
        create_application_history(conn, j1)
        create_application_history(conn, j2)
    assert _kpis(db_path)["application_count"] == 2


def test_response_rate(db_path):
    j1, j2 = _job(db_path, "A"), _job(db_path, "B")
    with session(db_path) as conn:
        r1 = create_application_history(conn, j1)
        create_application_history(conn, j2)
        record_response(conn, r1, "質問", "テスト")
    kpis = _kpis(db_path)
    assert kpis["response_count"] == 1
    assert kpis["response_rate"] == 50.0


def test_interview_rate(db_path):
    j1, j2 = _job(db_path, "A"), _job(db_path, "B")
    with session(db_path) as conn:
        r1 = create_application_history(conn, j1)
        create_application_history(conn, j2)
        create_interview(conn, r1, scheduled_start="2026-07-20 10:00:00")
    kpis = _kpis(db_path)
    assert kpis["interview_count"] == 1
    assert kpis["interview_rate"] == 50.0


def test_hired_and_contracted_rate(db_path):
    job_ids = [_job(db_path, t) for t in ("A", "B", "C", "D")]
    with session(db_path) as conn:
        r1 = create_application_history(conn, job_ids[0])
        for jid in job_ids[1:]:
            create_application_history(conn, jid)
        record_hired(conn, r1, contract_amount=30000)
    kpis = _kpis(db_path)
    assert kpis["hired_count"] == 1
    assert kpis["hired_rate"] == 25.0
    assert kpis["contracted_count"] == 1
    assert kpis["contracted_rate"] == 25.0
    assert kpis["contract_amount_total"] == 30000


def test_denominator_zero_returns_none(db_path):
    kpis = _kpis(db_path)
    assert kpis["application_count"] == 0
    assert kpis["response_rate"] is None
    assert kpis["hired_rate"] is None
    assert kpis["contract_amount_avg"] is None


def test_multiple_responses_counted_once_per_application(db_path):
    job = _job(db_path, "A")
    with session(db_path) as conn:
        r1 = create_application_history(conn, job)
        record_response(conn, r1, "質問", "質問1")
        record_response(conn, r1, "面談依頼", "質問2")
    kpis = _kpis(db_path)
    assert kpis["application_count"] == 1
    assert kpis["response_count"] == 1
    assert kpis["response_rate"] == 100.0


def test_multiple_interviews_counted_once_per_application(db_path):
    job = _job(db_path, "A")
    with session(db_path) as conn:
        r1 = create_application_history(conn, job)
        create_interview(conn, r1, scheduled_start="2026-07-20 10:00:00")
        create_interview(conn, r1, scheduled_start="2026-07-25 10:00:00")
    kpis = _kpis(db_path)
    assert kpis["interview_count"] == 1
    assert kpis["interview_rate"] == 100.0


def test_rejected_and_withdrawn_counts(db_path):
    j1, j2 = _job(db_path, "A"), _job(db_path, "B")
    with session(db_path) as conn:
        r1 = create_application_history(conn, j1)
        create_application_history(conn, j2)
        record_rejected(conn, r1, client_reason="金額")
    kpis = _kpis(db_path)
    assert kpis["rejected_count"] == 1
