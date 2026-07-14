"""第3段階: 営業文自動生成機能テーブルのマイグレーションのテスト。"""
from __future__ import annotations

from src.database import init_db, session
from src.repositories import insert_job, save_job_analysis


def test_migration_creates_application_tables(db_path):
    with session(db_path) as conn:
        tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    expected = {
        "application_drafts", "application_versions", "application_templates",
        "pricing_settings", "application_checklists", "portfolio_matches",
    }
    assert expected.issubset(tables)


def test_migration_is_idempotent(db_path):
    init_db(db_path)
    init_db(db_path)  # 例外が発生しないこと


def test_portfolios_table_has_new_columns(db_path):
    with session(db_path) as conn:
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(portfolios)")}
    expected = {
        "portfolio_type", "main_category", "subcategories_json", "target_job_categories_json",
        "design_tools_json", "technology_keywords_json", "sales_description", "priority",
        "for_development", "for_design", "for_ai_design", "display_order",
    }
    assert expected.issubset(columns)


def test_ai_dev_and_design_and_github_portfolios_seeded(db_path):
    with session(db_path) as conn:
        titles = {r["title"] for r in conn.execute("SELECT title FROM portfolios")}
    assert "AIエンジニア・Web制作ポートフォリオ" in titles
    assert "グラフィック・Webデザイン ポートフォリオ" in titles
    assert "GitHub" in titles


def test_foriio_url_registered_correctly(db_path):
    with session(db_path) as conn:
        row = conn.execute(
            "SELECT portfolio_url FROM portfolios WHERE title = 'グラフィック・Webデザイン ポートフォリオ'"
        ).fetchone()
    assert row["portfolio_url"] == "https://www.foriio.com/rilymoe0902"


def test_ai_dev_portfolio_url_registered_correctly(db_path):
    with session(db_path) as conn:
        row = conn.execute(
            "SELECT portfolio_url FROM portfolios WHERE title = 'AIエンジニア・Web制作ポートフォリオ'"
        ).fetchone()
    assert row["portfolio_url"] == "https://moedaichi0629-ai.github.io/landing-page/"


def test_github_url_registered_correctly(db_path):
    with session(db_path) as conn:
        row = conn.execute("SELECT github_url FROM portfolios WHERE title = 'GitHub'").fetchone()
    assert row["github_url"] == "https://github.com/moedaichi0629-ai"


def test_no_duplicate_portfolios_after_repeated_migration(db_path):
    init_db(db_path)
    init_db(db_path)
    with session(db_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM portfolios WHERE title = 'AIエンジニア・Web制作ポートフォリオ'"
        ).fetchone()[0]
    assert count == 1


def test_default_templates_and_pricing_settings_seeded(db_path):
    with session(db_path) as conn:
        template_count = conn.execute("SELECT COUNT(*) FROM application_templates").fetchone()[0]
        pricing_count = conn.execute("SELECT COUNT(*) FROM pricing_settings").fetchone()[0]
    assert template_count > 0
    assert pricing_count > 0


def test_existing_analysis_data_preserved_across_migration(db_path):
    with session(db_path) as conn:
        job_id = insert_job(conn, {"title": "既存案件", "source_type": "manual"})
        save_job_analysis(conn, job_id, {
            "rule_based_score": 70, "total_score": 75, "safety_score": 90, "risk_level": "low",
            "used_ai": 0,
        })

    init_db(db_path)  # マイグレーションを再実行

    with session(db_path) as conn:
        rows = conn.execute("SELECT total_score FROM job_analyses WHERE job_id = ?", (job_id,)).fetchall()
    assert any(r["total_score"] == 75 for r in rows)


def test_existing_portfolio_manual_edit_not_overwritten(db_path):
    with session(db_path) as conn:
        conn.execute(
            "UPDATE portfolios SET portfolio_url = ? WHERE title = 'AI ToDoリスト'",
            ("https://user-edited-url.example.com/",),
        )

    init_db(db_path)  # マイグレーションを再実行しても、ユーザーが入力済みのURLは上書きしない

    with session(db_path) as conn:
        row = conn.execute("SELECT portfolio_url FROM portfolios WHERE title = 'AI ToDoリスト'").fetchone()
    assert row["portfolio_url"] == "https://user-edited-url.example.com/"
