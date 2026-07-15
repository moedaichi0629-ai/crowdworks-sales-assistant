"""スコア帯別・クライアント情報別分析のテスト。"""
from __future__ import annotations

from src.analytics.kpi_service import get_base_records
from src.analytics.period_service import PERIOD_ALL, resolve_period
from src.analytics.result_analytics import analyze_by_client_info
from src.analytics.score_analytics import analyze_by_total_score
from src.crm.application_history_service import create_application_history
from src.database import session
from src.repositories import insert_job, list_jobs_with_analysis_for_scoring, save_job_analysis


def _job(db_path, title, total_score, client_rating=None, identity_verified=0, applicant_count=None) -> int:
    with session(db_path) as conn:
        job_id = insert_job(conn, {
            "title": title, "body": "x" * 50, "source_type": "manual",
            "client_rating": client_rating, "identity_verified": identity_verified,
            "applicant_count": applicant_count,
        })
        save_job_analysis(conn, job_id, {
            "rule_based_score": 70, "ai_suitability_score": 80, "total_score": total_score,
            "safety_score": 90, "risk_level": "low", "used_ai": 0,
        })
        return job_id


def _records(db_path) -> list[dict]:
    with session(db_path) as conn:
        d_from, d_to = resolve_period(PERIOD_ALL)
        return get_base_records(conn, d_from, d_to)


def test_score_band_bucketing_includes_job_count(db_path):
    j1 = _job(db_path, "高スコア", 95)
    j2 = _job(db_path, "中スコア", 65)
    with session(db_path) as conn:
        create_application_history(conn, j1)
        create_application_history(conn, j2)

    with session(db_path) as conn:
        jobs = list_jobs_with_analysis_for_scoring(conn)
    by_score = analyze_by_total_score(_records(db_path), jobs)
    assert by_score["90〜100"]["application_count"] == 1
    assert by_score["90〜100"]["job_count"] == 1
    assert by_score["60〜69"]["application_count"] == 1


def test_identity_verified_comparison(db_path):
    j1 = _job(db_path, "本人確認済み", 80, identity_verified=1)
    j2 = _job(db_path, "未確認", 80, identity_verified=0)
    with session(db_path) as conn:
        create_application_history(conn, j1)
        create_application_history(conn, j2)

    info = analyze_by_client_info(_records(db_path))
    assert info["identity_verified"]["application_count"] == 1
    assert info["identity_unverified"]["application_count"] == 1


def test_rating_band_bucketing(db_path):
    j1 = _job(db_path, "高評価", 80, client_rating=4.8)
    j2 = _job(db_path, "低評価", 80, client_rating=3.0)
    with session(db_path) as conn:
        create_application_history(conn, j1)
        create_application_history(conn, j2)

    info = analyze_by_client_info(_records(db_path))
    assert info["by_rating"]["評価4.5以上"]["application_count"] == 1
    assert info["by_rating"]["評価3.5未満"]["application_count"] == 1


def test_applicant_count_band_bucketing(db_path):
    j1 = _job(db_path, "少人数", 80, applicant_count=3)
    j2 = _job(db_path, "多人数", 80, applicant_count=30)
    with session(db_path) as conn:
        create_application_history(conn, j1)
        create_application_history(conn, j2)

    info = analyze_by_client_info(_records(db_path))
    assert info["by_applicant_count"]["0〜5人"]["application_count"] == 1
    assert info["by_applicant_count"]["21〜50人"]["application_count"] == 1
