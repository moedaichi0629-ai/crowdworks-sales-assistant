"""ポートフォリオ自動選択(portfolio_matcher)のテスト。"""
from __future__ import annotations

from src.portfolio.portfolio_matcher import MAX_SELECTIONS, select_portfolios


def _pf(id_, title, **kwargs) -> dict:
    base = {
        "id": id_, "title": title, "is_active": True, "priority": 50,
        "for_development": False, "for_design": False, "for_ai_design": False,
        "technology_keywords": [], "design_tools": [], "skills": [], "technologies": [],
        "subcategories": [], "target_job_categories": [], "portfolio_url": None, "github_url": None,
    }
    base.update(kwargs)
    return base


AI_DEV_PF = _pf(
    1, "AIエンジニア・Web制作ポートフォリオ", for_development=True, for_ai_design=True,
    technology_keywords=["AI", "Python", "React", "API", "業務自動化"],
    target_job_categories=["AI関連案件", "Web開発案件"], portfolio_url="https://example.com/ai",
)
DESIGN_PF = _pf(
    2, "グラフィック・Webデザイン ポートフォリオ", for_design=True, for_ai_design=True,
    technology_keywords=["Illustrator", "Photoshop", "バナー", "ロゴ", "Webデザイン"],
    target_job_categories=["バナー制作案件", "ロゴ制作案件"], portfolio_url="https://foriio.example/design",
)
GITHUB_PF = _pf(
    3, "GitHub", for_development=True, technology_keywords=[], github_url="https://github.com/example",
    target_job_categories=["AI案件", "技術力の確認が必要な案件"],
)
UNRELATED_PF = _pf(4, "無関係な実績", for_development=True, technology_keywords=["COBOL", "メインフレーム"])


def test_ai_job_selects_ai_portfolio():
    job = {"title": "AIツール開発案件", "body": "PythonとAPIを使ってAIツールを開発してください。", "category": "AI開発"}
    result = select_portfolios(job, [AI_DEV_PF, DESIGN_PF, GITHUB_PF, UNRELATED_PF])
    selected = [r for r in result if r["is_selected"]]
    assert any(r["portfolio_id"] == 1 for r in selected)


def test_api_job_makes_github_a_candidate():
    job = {"title": "API連携案件", "body": "外部APIとの連携をお願いします。技術力を確認できるものがあれば教えてください。", "category": "API連携"}
    result = select_portfolios(job, [AI_DEV_PF, DESIGN_PF, GITHUB_PF])
    ids = [r["portfolio_id"] for r in result if r["relevance_score"] > 0]
    assert 3 in ids


def test_design_job_prioritizes_foriio():
    job = {"title": "バナー制作案件", "body": "SNS用のバナーをIllustratorで制作してください。", "category": "デザイン"}
    result = select_portfolios(job, [AI_DEV_PF, DESIGN_PF, GITHUB_PF])
    top = result[0]
    assert top["portfolio_id"] == 2
    assert top["is_selected"] is True


def test_sns_image_job_selects_design_portfolio():
    job = {"title": "SNS投稿画像制作", "body": "Instagram用の投稿画像を作成してください。バナーデザインの経験がある方歓迎です。", "category": "デザイン"}
    result = select_portfolios(job, [AI_DEV_PF, DESIGN_PF])
    selected_ids = [r["portfolio_id"] for r in result if r["is_selected"]]
    assert 2 in selected_ids


def test_logo_job_selects_design_portfolio():
    job = {"title": "ロゴ制作案件", "body": "会社のロゴをデザインしてください。", "category": "デザイン"}
    result = select_portfolios(job, [AI_DEV_PF, DESIGN_PF])
    assert result[0]["portfolio_id"] == 2


def test_web_design_job_selects_design_portfolio():
    job = {"title": "Webデザイン案件", "body": "サイトのWebデザインをお願いします。", "category": "デザイン"}
    result = select_portfolios(job, [AI_DEV_PF, DESIGN_PF])
    assert result[0]["portfolio_id"] == 2


def test_web_implementation_job_selects_ai_dev_portfolio():
    job = {"title": "Webアプリ開発案件", "body": "ReactとPythonでWebアプリを開発してください。業務自動化もお願いします。", "category": "開発"}
    result = select_portfolios(job, [AI_DEV_PF, DESIGN_PF])
    assert result[0]["portfolio_id"] == 1


def test_ai_design_combined_job_selects_both():
    job = {
        "title": "AIを使用した画像制作案件",
        "body": "AIデザインでバナーを制作し、PythonでAI画像生成システムも構築してください。Illustratorでの仕上げもお願いします。",
        "category": "AI×デザイン",
    }
    result = select_portfolios(job, [AI_DEV_PF, DESIGN_PF, GITHUB_PF])
    selected_ids = {r["portfolio_id"] for r in result if r["is_selected"]}
    assert 1 in selected_ids
    assert 2 in selected_ids


def test_required_skill_match_increases_score():
    job = {"title": "案件", "body": "AI Python React", "category": ""}
    result = select_portfolios(job, [AI_DEV_PF])
    assert result[0]["matched_skills"]
    assert result[0]["relevance_score"] > 0


def test_max_three_selections():
    portfolios = [
        _pf(i, f"実績{i}", for_development=True, technology_keywords=["AI", "Python", "API", "業務自動化"])
        for i in range(1, 8)
    ]
    job = {"title": "AI開発案件", "body": "AI Python API 業務自動化", "category": "AI開発"}
    result = select_portfolios(job, portfolios)
    selected = [r for r in result if r["is_selected"]]
    assert len(selected) <= MAX_SELECTIONS


def test_low_relevance_portfolio_not_selected():
    job = {"title": "データ入力案件", "body": "Excelへのデータ入力作業です。", "category": "データ入力"}
    result = select_portfolios(job, [UNRELATED_PF])
    assert all(not r["is_selected"] for r in result)


def test_portfolio_without_url_can_still_be_scored_but_not_fabricated():
    pf_no_url = _pf(9, "URLなし実績", for_development=True, technology_keywords=["AI", "Python"])
    job = {"title": "AI開発案件", "body": "AI Python を使った開発", "category": "AI"}
    result = select_portfolios(job, [pf_no_url])
    assert result[0]["portfolio_id"] == 9
    # URLを持たないポートフォリオでも relevance は計算されるが、URLを捏造しない
    assert pf_no_url["portfolio_url"] is None
    assert pf_no_url["github_url"] is None


def test_manual_selection_is_preserved():
    job = {"title": "AI開発案件", "body": "AI Python", "category": "AI"}
    result = select_portfolios(job, [AI_DEV_PF, DESIGN_PF, GITHUB_PF], manual_selected_ids=[2, 3])
    selected = {r["portfolio_id"]: r["selection_order"] for r in result if r["is_selected"]}
    assert selected == {2: 0, 3: 1}


def test_no_duplicate_selection():
    job = {"title": "AI開発案件", "body": "AI Python API 業務自動化", "category": "AI開発"}
    result = select_portfolios(job, [AI_DEV_PF, DESIGN_PF, GITHUB_PF])
    ids = [r["portfolio_id"] for r in result if r["is_selected"]]
    assert len(ids) == len(set(ids))


def test_inactive_portfolio_excluded():
    inactive_pf = _pf(5, "非公開実績", is_active=False, for_development=True, technology_keywords=["AI", "Python"])
    job = {"title": "AI開発案件", "body": "AI Python", "category": "AI"}
    result = select_portfolios(job, [inactive_pf])
    assert result == []
