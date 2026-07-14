"""AI APIなしでの営業文テンプレート生成(template_generator)のテスト。"""
from __future__ import annotations

from src.application.template_generator import (
    DEFAULT_TEMPLATE_DEFINITIONS,
    TEMPLATE_CATEGORIES,
    detect_template_category,
    generate_from_template,
    recommend_tone,
)
from src.config import DEFAULT_MAX_APPLICATION_CHARS, LENGTH_STANDARD

_SKILLS = [
    {"skill_name": "Python", "experience_type": "個人開発"},
    {"skill_name": "Illustrator", "experience_type": "公開実績"},
]
_PROFILE = {"display_name": "テストユーザー", "job_title": "AIエンジニア", "experience_level": "学習中"}


def _price_info(**kwargs):
    base = {"proposed_price": 10000, "price_reason": "テスト理由", "is_uncertain": False}
    base.update(kwargs)
    return base


def _delivery_info(**kwargs):
    base = {"recommended_delivery_days": 7, "delivery_reason": "テスト理由", "pre_confirmation_items": [], "warnings": []}
    base.update(kwargs)
    return base


def test_detect_category_for_banner_job():
    job = {"title": "バナー制作をお願いします", "body": "SNS用のバナー", "category": ""}
    assert detect_template_category(job) == "バナー制作"


def test_detect_category_for_ai_job():
    job = {"title": "AI開発案件", "body": "ChatGPTを使った開発", "category": ""}
    assert detect_template_category(job) == "AI開発"


def test_detect_category_for_ai_design_combo():
    job = {"title": "AIを使用した画像制作", "body": "PythonでAI画像生成し、Illustratorで仕上げるバナー制作", "category": ""}
    assert detect_template_category(job) == "AI×デザイン"


def test_detect_category_fallback_other():
    job = {"title": "その他の作業", "body": "特に技術要件のない作業です。", "category": ""}
    assert detect_template_category(job) == "その他"


def test_recommend_tone_matches_category():
    assert recommend_tone("バナー制作") is not None
    assert recommend_tone("ホームページ制作") is not None


def test_generate_from_template_design_job_includes_only_design_portfolio_url():
    job = {"title": "バナー制作", "body": "SNS用バナーを制作してください。予算は5000円です。"}
    design_pf = {
        "id": 2, "title": "デザインポートフォリオ", "portfolio_type": "design",
        "portfolio_url": "https://foriio.example/design", "github_url": None,
        "sales_description": "デザイン実績です。",
    }
    result = generate_from_template(
        job, _PROFILE, _SKILLS, [design_pf], _price_info(), _delivery_info(), [],
        length_type=LENGTH_STANDARD,
    )
    assert "https://foriio.example/design" in result["full_message"]
    assert "github.com" not in result["full_message"]


def test_generate_from_template_no_portfolio_says_no_related_work():
    job = {"title": "特殊な専門案件", "body": "非常に特殊な専門知識が必要です。"}
    result = generate_from_template(job, _PROFILE, _SKILLS, [], _price_info(), _delivery_info(), [])
    assert "関連実績なし" in result["full_message"]
    # 虚偽のURLを含まない
    assert "http" not in result["full_message"]


def test_generate_from_template_does_not_fabricate_real_job_experience():
    job = {"title": "Python開発案件", "body": "Pythonでの開発をお願いします。"}
    result = generate_from_template(job, _PROFILE, _SKILLS, [], _price_info(), _delivery_info(), [])
    assert "実務で多数" not in result["full_message"]
    assert "実務経験が豊富" not in result["full_message"]


def test_generate_from_template_answers_client_questions():
    job = {"title": "デザイン案件", "body": "Illustratorでの制作経験を教えてください。"}
    client_questions = [{"question": "Illustratorでの制作経験を教えてください", "answer_category": "design"}]
    result = generate_from_template(job, _PROFILE, _SKILLS, [], _price_info(), _delivery_info(), client_questions)
    assert result["answers_to_client_questions"]
    assert result["answers_to_client_questions"][0]["question"] == client_questions[0]["question"]


def test_char_count_reported_and_within_reasonable_bound():
    job = {"title": "AI開発案件", "body": "AIチャットボットを開発してください。"}
    result = generate_from_template(job, _PROFILE, _SKILLS, [], _price_info(), _delivery_info(), [], length_type=LENGTH_STANDARD)
    assert len(result["full_message"]) > 0
    assert len(result["full_message"]) < DEFAULT_MAX_APPLICATION_CHARS


def test_all_template_categories_have_default_definitions():
    names = {t["category"] for t in DEFAULT_TEMPLATE_DEFINITIONS}
    assert names == set(TEMPLATE_CATEGORIES)


def test_tone_affects_closing_sentence():
    job = {"title": "AI開発案件", "body": "AI開発をお願いします。"}
    result_polite = generate_from_template(job, _PROFILE, _SKILLS, [], _price_info(), _delivery_info(), [], tone="丁寧")
    result_short = generate_from_template(job, _PROFILE, _SKILLS, [], _price_info(), _delivery_info(), [], tone="短め")
    assert result_polite["closing"] != result_short["closing"]
