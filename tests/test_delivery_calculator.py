"""納期提案(delivery_calculator)のテスト。"""
from __future__ import annotations

from src.delivery.delivery_calculator import compute_delivery_suggestion


def test_delivery_uses_estimated_hours_and_daily_hours():
    job = {"title": "AI開発", "body": "AI開発案件です。"}
    result = compute_delivery_suggestion(job, estimated_hours_min=10, estimated_hours_max=10, daily_available_hours=2.0)
    assert result["required_work_days"] == 5.0
    assert result["safe_delivery_days"] >= result["minimum_delivery_days"]


def test_unknown_work_amount_uses_fallback_and_warns():
    job = {"title": "案件", "body": "詳細は応相談です。"}
    result = compute_delivery_suggestion(job)
    assert result["warnings"]
    assert any("応募後にすり合わせ" in w for w in result["warnings"])


def test_design_job_adds_buffer_and_pre_confirmation():
    job = {"title": "バナー制作", "body": "バナーをデザインしてください。"}
    result = compute_delivery_suggestion(job, estimated_hours_min=4, estimated_hours_max=4, daily_available_hours=2.0)
    assert result["safe_delivery_days"] > result["minimum_delivery_days"] - 1
    assert any("デザイン" in item for item in result["pre_confirmation_items"])


def test_material_wait_keyword_adds_pre_confirmation():
    job = {"title": "チラシ制作", "body": "素材を提供しますので、チラシを作成してください。"}
    result = compute_delivery_suggestion(job, estimated_hours_min=3, estimated_hours_max=3)
    assert any("素材" in item for item in result["pre_confirmation_items"])


def test_api_review_keyword_adds_buffer():
    job = {"title": "LINE連携", "body": "LINE APIとの連携をお願いします。"}
    result_with_api = compute_delivery_suggestion(job, estimated_hours_min=5, estimated_hours_max=5, daily_available_hours=2.5)
    job_no_api = {"title": "作業", "body": "作業をお願いします。"}
    result_without_api = compute_delivery_suggestion(job_no_api, estimated_hours_min=5, estimated_hours_max=5, daily_available_hours=2.5)
    assert result_with_api["safe_delivery_days"] >= result_without_api["safe_delivery_days"]


def test_difficult_difficulty_adds_warning():
    job = {"title": "高度なシステム開発", "body": "高度なシステムを構築してください。"}
    result = compute_delivery_suggestion(job, estimated_hours_min=5, estimated_hours_max=5, difficulty="expert")
    assert any("難易度が高い" in w for w in result["warnings"])


def test_short_deadline_triggers_warning():
    import datetime as dt
    tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    job = {"title": "急ぎの案件", "body": "急ぎでお願いします。", "deadline": tomorrow}
    result = compute_delivery_suggestion(job, estimated_hours_min=20, estimated_hours_max=20, daily_available_hours=2.0)
    assert any("残り日数" in w for w in result["warnings"])


def test_concurrent_jobs_add_buffer():
    job = {"title": "案件", "body": "作業をお願いします。"}
    base = compute_delivery_suggestion(job, estimated_hours_min=5, estimated_hours_max=5, concurrent_job_count=0)
    busy = compute_delivery_suggestion(job, estimated_hours_min=5, estimated_hours_max=5, concurrent_job_count=2)
    assert busy["safe_delivery_days"] >= base["safe_delivery_days"]
