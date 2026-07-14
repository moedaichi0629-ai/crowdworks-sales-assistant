"""AI案件分析用テーブルのマイグレーションのテスト。"""
from __future__ import annotations

from src.database import init_db, session
from src.repositories import upsert_job


def test_migration_creates_new_tables(db_path):
    with session(db_path) as conn:
        tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"job_analyses", "user_profiles", "skills", "portfolios", "analysis_settings"}.issubset(tables)


def test_migration_is_idempotent(db_path):
    init_db(db_path)
    init_db(db_path)  # 例外が発生しないこと


def test_migration_seeds_default_profile_only_once(db_path):
    with session(db_path) as conn:
        count1 = conn.execute("SELECT COUNT(*) FROM user_profiles").fetchone()[0]
    init_db(db_path)
    init_db(db_path)
    with session(db_path) as conn:
        count2 = conn.execute("SELECT COUNT(*) FROM user_profiles").fetchone()[0]
    assert count1 == 1
    assert count2 == 1


def test_existing_job_data_preserved_across_migration(db_path):
    with session(db_path) as conn:
        upsert_job(conn, {"title": "既存案件", "url": "https://example.com/x"})

    init_db(db_path)  # マイグレーションを再実行

    with session(db_path) as conn:
        rows = conn.execute("SELECT title FROM jobs").fetchall()
    assert any(r["title"] == "既存案件" for r in rows)


def test_skills_and_portfolios_seeded(db_path):
    with session(db_path) as conn:
        skill_count = conn.execute("SELECT COUNT(*) FROM skills").fetchone()[0]
        portfolio_count = conn.execute("SELECT COUNT(*) FROM portfolios").fetchone()[0]
    assert skill_count > 0
    # 第2段階の7件 + 第3段階で追加されるAI・開発/デザイン/GitHubポートフォリオ3件 = 10件
    assert portfolio_count == 10
