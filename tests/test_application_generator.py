"""営業文生成オーケストレーション(application_generator)のテスト。

実際の有料APIは呼び出さず、requests.post をモックして検証する。
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.application.application_generator import GenerationBlockedError, generate_application
from src.database import session
from src.repositories import get_job, get_profile_bundle, insert_job, list_portfolios


def _insert_design_job(db_path) -> int:
    job = {
        "title": "バナー制作案件（Illustrator使用）",
        "description": "SNS投稿用バナーを作成してください。",
        "body": "Instagram広告用のバナーを5枚制作してください。Illustratorでの制作経験がある方歓迎です。"
                "デザインポートフォリオがあれば教えてください。予算は10000円〜20000円です。",
        "job_type": "固定報酬制", "category": "デザイン", "budget_min": 10000, "budget_max": 20000,
        "budget_text": "10000円〜20000円", "applicant_count": 3, "client_name": "テスト株式会社",
        "client_rating": 4.8, "identity_verified": 1, "source_type": "manual",
    }
    with session(db_path) as conn:
        return insert_job(conn, job)


def test_template_generation_selects_design_portfolio_and_url(db_path):
    job_id = _insert_design_job(db_path)
    with session(db_path) as conn:
        job = get_job(conn, job_id)
        bundle = get_profile_bundle(conn)
        result = generate_application(conn, job, bundle, None, None, generation_type="template")

    assert result["generation_type"] == "template"
    assert "https://www.foriio.com/rilymoe0902" in result["full_message"]
    assert "github.com" not in result["full_message"]


def test_generation_blocked_for_dangerous_job(db_path):
    job = {
        "title": "副業案件", "description": "簡単に稼げます",
        "body": "初期費用として登録費用が必要です。教材購入をお願いします。誰でも稼げる高収入案件です。",
        "job_type": "固定報酬制", "category": "その他", "source_type": "manual",
    }
    with session(db_path) as conn:
        job_id = insert_job(conn, job)
    with session(db_path) as conn:
        job = get_job(conn, job_id)
        bundle = get_profile_bundle(conn)
        with pytest.raises(GenerationBlockedError):
            generate_application(conn, job, bundle, None, None, generation_type="template")


def test_ai_generation_sanitizes_fabricated_url_and_guarantee(db_path):
    job_id = _insert_design_job(db_path)

    with session(db_path) as conn:
        bundle = get_profile_bundle(conn)
        portfolios = list_portfolios(conn, bundle["profile"]["id"])
        design_pf_id = next(p["id"] for p in portfolios if p["title"] == "グラフィック・Webデザイン ポートフォリオ")

    fake_response = {
        "application_title": "バナー制作案件への応募", "opening": "拝見し応募しました。",
        "understanding": "内容を理解しました。", "matching_reason": "デザイン経験があります。",
        "skills_to_highlight": ["Illustrator"], "portfolio_ids": [design_pf_id],
        "portfolio_reasons": ["デザイン実績と一致"], "proposed_approach": ["ヒアリングします"],
        "proposed_price": 15000, "price_reason": "予算内", "proposed_delivery_days": 10,
        "delivery_reason": "作業量を踏まえて", "answers_to_client_questions": ["経験があります"],
        "questions_for_client": [], "closing": "よろしくお願いします。",
        "full_message": "デザイン経験があります。必ず売上を保証します。詳細: https://fake-unregistered-url.example.com/",
        "short_message": "応募します。", "warnings": [], "missing_information": [], "confidence": 60,
    }

    with patch("src.ai.openai_client.requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": json.dumps(fake_response, ensure_ascii=False)}}],
            "usage": {"total_tokens": 300},
        }
        mock_post.return_value = mock_response

        from src.ai.openai_client import OpenAIClient
        client = OpenAIClient(api_key="test-key", model="gpt-4o-mini")

        with session(db_path) as conn:
            job = get_job(conn, job_id)
            bundle = get_profile_bundle(conn)
            result = generate_application(conn, job, bundle, None, client, generation_type="ai")

    assert result["generation_type"] == "ai"
    assert "fake-unregistered-url.example.com" not in result["full_message"]
    assert any("保証" in w or "必ず売上" in w for w in result["warnings"])
    assert result["proposed_price"] == 15000


def test_ai_failure_falls_back_to_template(db_path):
    job_id = _insert_design_job(db_path)

    with patch("src.ai.openai_client.requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response

        from src.ai.openai_client import OpenAIClient
        client = OpenAIClient(api_key="test-key", model="gpt-4o-mini", max_retry_count=0)

        with session(db_path) as conn:
            job = get_job(conn, job_id)
            bundle = get_profile_bundle(conn)
            result = generate_application(conn, job, bundle, None, client, generation_type="ai")

    assert result["generation_type"] == "template_fallback"
    assert result["analysis_error"] is not None
    assert result["full_message"]


def test_price_and_delivery_override_applied(db_path):
    job_id = _insert_design_job(db_path)
    with session(db_path) as conn:
        job = get_job(conn, job_id)
        bundle = get_profile_bundle(conn)
        result = generate_application(
            conn, job, bundle, None, None, generation_type="template",
            price_override=99999, delivery_days_override=3,
        )
    assert result["proposed_price"] == 99999
    assert result["proposed_delivery_days"] == 3
