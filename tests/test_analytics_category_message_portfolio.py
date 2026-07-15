"""ジャンル・営業文・ポートフォリオ別分析のテスト。"""
from __future__ import annotations

from src.analytics.category_analytics import analyze_by_category_group, analyze_by_subcategory
from src.analytics.data_quality_service import check_data_quality
from src.analytics.kpi_service import get_base_records
from src.analytics.message_analytics import LOW_SAMPLE_THRESHOLD, analyze_by_tone
from src.analytics.period_service import PERIOD_ALL, resolve_period
from src.analytics.portfolio_analytics import analyze_by_portfolio
from src.application.application_generator import generate_application
from src.crm.application_history_service import create_application_history
from src.database import session
from src.repositories import (
    create_application_draft,
    get_job,
    get_profile_bundle,
    insert_job,
    list_portfolios,
    save_job_analysis,
    update_application_record,
)


def _job(db_path, title, category, body=None) -> int:
    with session(db_path) as conn:
        job_id = insert_job(conn, {
            "title": title, "body": body or (title + "x" * 40), "category": category, "source_type": "manual",
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


def test_category_group_classification(db_path):
    ai_job = _job(db_path, "AI業務自動化ツール開発案件", "AI開発", body="PythonとOpenAI APIで業務自動化ツールを開発してください。")
    design_job = _job(db_path, "バナー制作案件", "デザイン", body="Illustratorでバナー・SNS投稿画像を制作してください。")
    with session(db_path) as conn:
        create_application_history(conn, ai_job)
        create_application_history(conn, design_job)

    by_group = analyze_by_category_group(_records(db_path))
    assert by_group["AI・開発"]["application_count"] == 1
    assert by_group["デザイン"]["application_count"] == 1


def test_subcategory_classification(db_path):
    job = _job(db_path, "バナー制作案件（Illustrator使用）", "デザイン")
    with session(db_path) as conn:
        create_application_history(conn, job)

    sub = analyze_by_subcategory(_records(db_path))
    assert "バナー" in sub
    assert sub["バナー"]["application_count"] == 1


def test_tone_usage_and_reference_only_flag(db_path):
    job = _job(db_path, "テスト案件", "AI開発")
    with session(db_path) as conn:
        record_id = create_application_history(conn, job)
        update_application_record(conn, record_id, {"tone": "AI・開発案件向け", "sent_message": "x" * 100})

    by_tone = analyze_by_tone(_records(db_path))
    assert by_tone["AI・開発案件向け"]["usage_count"] == 1
    assert by_tone["AI・開発案件向け"]["usage_count"] < LOW_SAMPLE_THRESHOLD
    assert by_tone["AI・開発案件向け"]["is_reference_only"] is True


def test_missing_tone_not_counted_in_tone_analysis(db_path):
    job = _job(db_path, "テスト案件", "AI開発")
    with session(db_path) as conn:
        create_application_history(conn, job)  # toneは未設定のまま

    by_tone = analyze_by_tone(_records(db_path))
    assert by_tone == {}


def test_portfolio_multiple_selection_counted_for_each(db_path):
    job_id = _job(
        db_path, "AI×デザイン複合案件", "AI開発",
        body="AIを使ったバナー制作と業務自動化を行います。PythonとOpenAI APIを使用します。",
    )

    with session(db_path) as conn:
        job = get_job(conn, job_id)
        bundle = get_profile_bundle(conn)
        portfolios = list_portfolios(conn, bundle["profile"]["id"])
        pf_ids = [p["id"] for p in portfolios[:2]]
        result = generate_application(
            conn, job, bundle, None, None, generation_type="template", manual_portfolio_ids=pf_ids,
        )
        draft_data = {k: v for k, v in result.items() if k not in ("client_questions", "candidate_portfolios", "char_count")}
        draft_data["application_message"] = draft_data.pop("full_message")
        draft_id = create_application_draft(conn, job_id, draft_data)
        create_application_history(conn, job_id, application_draft_id=draft_id)

    records = _records(db_path)
    with session(db_path) as conn:
        by_portfolio = analyze_by_portfolio(conn, records)

    used_titles = [p["title"] for p in records[0]["portfolio_snapshot"]]
    assert len(used_titles) == 2
    for title in used_titles:
        assert by_portfolio[title]["usage_count"] == 1


def test_data_quality_detects_missing_tone_and_portfolio(db_path):
    job = _job(db_path, "テスト案件", "AI開発")
    with session(db_path) as conn:
        create_application_history(conn, job)

    quality = check_data_quality(_records(db_path))
    assert quality["missing_tone_count"] == 1
    assert quality["missing_portfolio_snapshot_count"] == 1
