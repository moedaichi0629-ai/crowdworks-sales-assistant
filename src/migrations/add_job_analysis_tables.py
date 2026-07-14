"""第2段階: AI案件分析機能のためのテーブルを追加するマイグレーション。

既存の jobs / settings / import_logs テーブルには変更を加えず、
分析結果・プロフィール情報は新規テーブルに分離して保存する
（要件で許可されている「分析結果を別テーブルへ分ける」推奨構成を採用）。

このマイグレーションは何度実行しても安全（CREATE TABLE IF NOT EXISTS、
初期プロフィールは未登録の場合のみ投入）。既存データは一切削除・変更しない。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from src.config import DB_PATH
from src.logger import get_logger

logger = get_logger()

ANALYSIS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS job_analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    content_hash TEXT,
    rule_based_score INTEGER,
    rule_based_breakdown_json TEXT,
    ai_suitability_score INTEGER,
    total_score INTEGER,
    recommendation TEXT,
    application_priority TEXT,
    difficulty TEXT,
    confidence_score INTEGER,
    summary TEXT,
    client_needs_json TEXT,
    required_skills_json TEXT,
    matched_skills_json TEXT,
    missing_skills_json TEXT,
    matched_portfolio_json TEXT,
    estimated_hours_min INTEGER,
    estimated_hours_max INTEGER,
    estimated_days INTEGER,
    budget_evaluation TEXT,
    strengths_json TEXT,
    concerns_json TEXT,
    questions_json TEXT,
    application_strategy TEXT,
    analysis_reason TEXT,
    safety_score INTEGER,
    risk_level TEXT,
    detected_risks_json TEXT,
    risk_reasons_json TEXT,
    recommended_action TEXT,
    safety_summary TEXT,
    provider TEXT,
    model TEXT,
    prompt_version TEXT,
    used_ai INTEGER NOT NULL DEFAULT 0,
    token_usage_json TEXT,
    analysis_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_job_analyses_job_id ON job_analyses (job_id);
CREATE INDEX IF NOT EXISTS idx_job_analyses_content_hash ON job_analyses (content_hash);
CREATE INDEX IF NOT EXISTS idx_job_analyses_created_at ON job_analyses (created_at);

CREATE TABLE IF NOT EXISTS user_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_name TEXT NOT NULL UNIQUE,
    display_name TEXT,
    job_title TEXT,
    experience_level TEXT,
    daily_available_hours TEXT,
    basic_info_json TEXT,
    preferred_conditions_json TEXT,
    difficult_conditions_json TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS skills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL,
    category TEXT,
    skill_name TEXT NOT NULL,
    proficiency_level TEXT,
    experience_type TEXT,
    years_experience REAL,
    memo TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_skills_profile_id ON skills (profile_id);

CREATE TABLE IF NOT EXISTS portfolios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    technologies_json TEXT,
    skills_json TEXT,
    portfolio_url TEXT,
    github_url TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_portfolios_profile_id ON portfolios (profile_id);

CREATE TABLE IF NOT EXISTS analysis_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    setting_key TEXT NOT NULL UNIQUE,
    setting_value TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
    ).fetchone()
    return row is not None


def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, column_def: str) -> None:
    """指定テーブルに列が存在しない場合のみ追加する（何度実行しても安全）。"""
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})")}
    if column_name not in columns:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_def}")


def run_migration(db_path: Path | str = DB_PATH) -> dict:
    """AI案件分析用テーブルを作成し、初期プロフィールを未登録の場合のみ投入する。

    複数回実行しても安全。既存の jobs/settings/import_logs データは変更しない。
    戻り値: {"tables_created": bool, "profile_seeded": bool}
    """
    from src.database import session  # 循環importを避けるため関数内でimport

    with session(db_path) as conn:
        already_had_job_analyses = _table_exists(conn, "job_analyses")
        conn.executescript(ANALYSIS_SCHEMA_SQL)
        if _table_exists(conn, "user_profiles"):
            _ensure_column(conn, "user_profiles", "version", "version INTEGER NOT NULL DEFAULT 1")

    logger.info("データベースマイグレーションを実行しました: add_job_analysis_tables")

    profile_seeded = _seed_default_profile_if_absent(db_path)

    return {
        "tables_created": not already_had_job_analyses,
        "profile_seeded": profile_seeded,
    }


def _seed_default_profile_if_absent(db_path: Path | str) -> bool:
    from src.database import session
    from src.profile.default_profile import (
        DEFAULT_PORTFOLIOS,
        DEFAULT_PROFILE,
        DEFAULT_SKILLS,
    )
    from src.utils import now_jst_str
    import json

    with session(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM user_profiles WHERE profile_name = ?", (DEFAULT_PROFILE["profile_name"],)
        ).fetchone()
        if existing is not None:
            return False

        now = now_jst_str()
        cursor = conn.execute(
            """
            INSERT INTO user_profiles
                (profile_name, display_name, job_title, experience_level, daily_available_hours,
                 basic_info_json, preferred_conditions_json, difficult_conditions_json,
                 is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                DEFAULT_PROFILE["profile_name"],
                DEFAULT_PROFILE["display_name"],
                DEFAULT_PROFILE["job_title"],
                DEFAULT_PROFILE["experience_level"],
                DEFAULT_PROFILE["daily_available_hours"],
                json.dumps(DEFAULT_PROFILE["basic_info"], ensure_ascii=False),
                json.dumps(DEFAULT_PROFILE["preferred_conditions"], ensure_ascii=False),
                json.dumps(DEFAULT_PROFILE["difficult_conditions"], ensure_ascii=False),
                now, now,
            ),
        )
        profile_id = cursor.lastrowid

        for skill in DEFAULT_SKILLS:
            conn.execute(
                """
                INSERT INTO skills
                    (profile_id, category, skill_name, proficiency_level, experience_type,
                     years_experience, memo, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile_id, skill["category"], skill["skill_name"],
                    skill.get("proficiency_level"), skill.get("experience_type"),
                    skill.get("years_experience"), skill.get("memo"), now, now,
                ),
            )

        for portfolio in DEFAULT_PORTFOLIOS:
            conn.execute(
                """
                INSERT INTO portfolios
                    (profile_id, title, description, technologies_json, skills_json,
                     portfolio_url, github_url, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    profile_id, portfolio["title"], portfolio.get("description"),
                    json.dumps(portfolio.get("technologies", []), ensure_ascii=False),
                    json.dumps(portfolio.get("skills", []), ensure_ascii=False),
                    portfolio.get("portfolio_url"), portfolio.get("github_url"),
                    now, now,
                ),
            )

    logger.info("初期スキルプロフィールを投入しました: profile=%s", DEFAULT_PROFILE["profile_name"])
    return True
