"""応募金額提案(price_calculator)のテスト。"""
from __future__ import annotations

from src.pricing.price_calculator import compute_price_suggestion


def test_hourly_job_type_uses_hourly_rate():
    job = {"title": "運用保守", "job_type": "時間単価制", "category": "", "budget_min": None, "budget_max": None}
    result = compute_price_suggestion(job)
    assert result["proposed_price"] >= 1200
    assert result["is_uncertain"] is False


def test_ai_api_hourly_job_uses_higher_rate():
    job = {"title": "AI API連携の運用保守", "job_type": "時間単価制", "category": "AI"}
    result = compute_price_suggestion(job)
    assert result["proposed_price"] >= 1200


def test_website_job_has_minimum_price():
    job = {"title": "ホームページ制作", "job_type": "固定報酬制", "category": "Web制作", "budget_min": 3000, "budget_max": 5000}
    result = compute_price_suggestion(job)
    assert result["proposed_price"] >= 5000  # 予算が最低金額未満でも最低金額を下回らない趣旨を確認
    assert result["minimum_price"] == 10000


def test_website_job_respects_budget_max_when_higher():
    job = {"title": "ホームページ制作", "job_type": "固定報酬制", "category": "Web制作", "budget_min": 20000, "budget_max": 30000}
    result = compute_price_suggestion(job)
    assert result["proposed_price"] <= 30000


def test_fixed_price_with_estimated_hours():
    job = {"title": "AI開発", "job_type": "固定報酬制", "category": "AI", "budget_min": None, "budget_max": None}
    result = compute_price_suggestion(job, estimated_hours_min=10, estimated_hours_max=20)
    assert result["proposed_price"] > 0
    assert result["is_uncertain"] is False


def test_uncertain_when_no_information():
    job = {"title": "作業", "job_type": "固定報酬制", "category": "", "budget_min": None, "budget_max": None}
    result = compute_price_suggestion(job)
    assert result["is_uncertain"] is True
    assert "目安" in result["price_reason"]


def test_never_below_minimum_order_price():
    job = {"title": "作業", "job_type": "固定報酬制", "category": "", "budget_min": 100, "budget_max": 500}
    result = compute_price_suggestion(job)
    assert result["proposed_price"] >= 3000
    assert result["minimum_price"] >= 3000


def test_category_price_note_applied():
    job = {"title": "バナー制作をお願いします", "job_type": "固定報酬制", "category": "デザイン", "budget_min": 5000, "budget_max": 8000}
    result = compute_price_suggestion(job)
    assert "バナー制作" in result["price_reason"]
    assert result["is_uncertain"] is True
