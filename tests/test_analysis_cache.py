"""分析結果キャッシュ(analysis_cache)のテスト。同一内容での不要な再分析を防止する。"""
from __future__ import annotations

from src.analysis.job_analyzer import analyze_job
from src.database import session
from src.repositories import (
    get_all_analysis_settings,
    get_job,
    get_profile_bundle,
    save_job_analysis,
    update_profile,
    upsert_job,
)


def _create_job(db_path) -> int:
    with session(db_path) as conn:
        _, job_id = upsert_job(
            conn,
            {
                "title": "テスト案件",
                "body": "Pythonでの業務自動化開発をお願いします。" * 3,
                "budget_text": "5万円",
                "deadline": "2026-08-01",
            },
        )
    return job_id


def test_cache_reused_for_identical_job_and_profile(db_path):
    job_id = _create_job(db_path)
    with session(db_path) as conn:
        job = get_job(conn, job_id)
        bundle = get_profile_bundle(conn)
        settings = get_all_analysis_settings(conn)

        result1 = analyze_job(conn, job, bundle, settings, None, exclude_keywords=[])
        save_job_analysis(conn, job_id, result1)

        result2 = analyze_job(conn, job, bundle, settings, None, exclude_keywords=[])

    assert result1["_from_cache"] is False
    assert result2["_from_cache"] is True


def test_cache_invalidated_when_body_changes(db_path):
    job_id = _create_job(db_path)
    with session(db_path) as conn:
        job = get_job(conn, job_id)
        bundle = get_profile_bundle(conn)
        settings = get_all_analysis_settings(conn)

        result1 = analyze_job(conn, job, bundle, settings, None, exclude_keywords=[])
        save_job_analysis(conn, job_id, result1)

        changed_job = dict(job)
        changed_job["body"] = "全く別の内容に変更された案件本文です。" * 3
        result2 = analyze_job(conn, changed_job, bundle, settings, None, exclude_keywords=[])

    assert result2["_from_cache"] is False


def test_cache_invalidated_when_profile_updated(db_path):
    job_id = _create_job(db_path)
    with session(db_path) as conn:
        job = get_job(conn, job_id)
        bundle = get_profile_bundle(conn)
        settings = get_all_analysis_settings(conn)

        result1 = analyze_job(conn, job, bundle, settings, None, exclude_keywords=[])
        save_job_analysis(conn, job_id, result1)

        update_profile(conn, bundle["profile"]["id"], {"job_title": "更新後の職種"})
        bundle2 = get_profile_bundle(conn)
        result2 = analyze_job(conn, job, bundle2, settings, None, exclude_keywords=[])

    assert result2["_from_cache"] is False


def test_force_reanalyze_ignores_cache(db_path):
    job_id = _create_job(db_path)
    with session(db_path) as conn:
        job = get_job(conn, job_id)
        bundle = get_profile_bundle(conn)
        settings = get_all_analysis_settings(conn)

        result1 = analyze_job(conn, job, bundle, settings, None, exclude_keywords=[])
        save_job_analysis(conn, job_id, result1)

        result2 = analyze_job(conn, job, bundle, settings, None, exclude_keywords=[], force_reanalyze=True)

    assert result2["_from_cache"] is False
