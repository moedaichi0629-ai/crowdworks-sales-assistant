"""第4段階Part1: 1日あたりの応募目標管理・本日の応募候補選定のためのテーブルを追加するマイグレーション。

新規テーブル: daily_application_goals / daily_candidates / application_records / daily_selection_settings。
既存の jobs / job_analyses / application_drafts / portfolios / analysis_settings 等の
データは一切削除・変更しない。何度実行しても安全（CREATE TABLE IF NOT EXISTS）。
"""
from __future__ import annotations

from pathlib import Path

from src.config import DB_PATH
from src.logger import get_logger
from src.migrations.add_job_analysis_tables import _table_exists

logger = get_logger()

DAILY_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS daily_application_goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_date TEXT NOT NULL UNIQUE,
    target_count INTEGER NOT NULL,
    maximum_count INTEGER NOT NULL,
    ai_development_target INTEGER NOT NULL,
    design_target INTEGER NOT NULL,
    other_target INTEGER NOT NULL,
    minimum_total_score INTEGER NOT NULL,
    minimum_ai_score INTEGER NOT NULL,
    minimum_safety_score INTEGER NOT NULL,
    allowed_risk_levels_json TEXT,
    new_arrival_hours INTEGER NOT NULL DEFAULT 48,
    maximum_applicant_count INTEGER NOT NULL DEFAULT 0,
    minimum_client_rating REAL NOT NULL DEFAULT 0,
    prioritize_verified_client INTEGER NOT NULL DEFAULT 1,
    prioritize_ready_drafts INTEGER NOT NULL DEFAULT 1,
    prioritize_application_written INTEGER NOT NULL DEFAULT 1,
    score_weights_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_daily_goals_target_date ON daily_application_goals (target_date);

CREATE TABLE IF NOT EXISTS daily_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_date TEXT NOT NULL,
    job_id INTEGER NOT NULL,
    application_draft_id INTEGER,
    category_group TEXT,
    daily_priority_score INTEGER NOT NULL DEFAULT 0,
    rank_number INTEGER,
    selection_reasons_json TEXT,
    exclusion_reasons_json TEXT,
    candidate_status TEXT NOT NULL DEFAULT '候補',
    is_manually_added INTEGER NOT NULL DEFAULT 0,
    is_manually_removed INTEGER NOT NULL DEFAULT 0,
    postponed_until TEXT,
    user_memo TEXT,
    selected_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_daily_candidates_target_date ON daily_candidates (target_date);
CREATE INDEX IF NOT EXISTS idx_daily_candidates_job_id ON daily_candidates (job_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_candidates_date_job ON daily_candidates (target_date, job_id);

CREATE TABLE IF NOT EXISTS application_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    application_draft_id INTEGER,
    applied_at TEXT NOT NULL,
    proposed_price INTEGER,
    proposed_delivery_days INTEGER,
    application_status TEXT NOT NULL DEFAULT '応募済み',
    is_over_limit INTEGER NOT NULL DEFAULT 0,
    over_limit_reason TEXT,
    user_memo TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_application_records_job_id ON application_records (job_id);
CREATE INDEX IF NOT EXISTS idx_application_records_applied_at ON application_records (applied_at);

CREATE TABLE IF NOT EXISTS daily_selection_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    setting_key TEXT NOT NULL UNIQUE,
    setting_value TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def run_migration(db_path: Path | str = DB_PATH) -> dict:
    """1日あたりの応募目標管理用テーブルを作成する。

    複数回実行しても安全。既存の jobs/job_analyses/application_drafts/portfolios/
    analysis_settings/pricing_settings データは一切変更・削除しない。
    """
    from src.database import session  # 循環importを避けるため関数内でimport

    with session(db_path) as conn:
        already_had_tables = _table_exists(conn, "daily_application_goals")
        conn.executescript(DAILY_SCHEMA_SQL)

    logger.info("データベースマイグレーションを実行しました: add_daily_application_tables")

    settings_seeded = _seed_default_daily_selection_settings_if_absent(db_path)

    return {
        "tables_created": not already_had_tables,
        "settings_seeded": settings_seeded,
    }


def _seed_default_daily_selection_settings_if_absent(db_path: Path | str) -> int:
    """応募目標のデフォルト値・デイリー優先スコアの重みを、未登録の場合のみ投入する。"""
    from src.config import DEFAULT_DAILY_GOAL_SETTINGS, DEFAULT_DAILY_SCORE_WEIGHTS
    from src.database import session
    from src.utils import now_jst_str
    import json

    seeded = 0
    now = now_jst_str()
    all_defaults: dict = {f"goal_default.{k}": v for k, v in DEFAULT_DAILY_GOAL_SETTINGS.items()}
    all_defaults.update({f"score_weight.{k}": v for k, v in DEFAULT_DAILY_SCORE_WEIGHTS.items()})

    with session(db_path) as conn:
        for key, value in all_defaults.items():
            existing = conn.execute(
                "SELECT id FROM daily_selection_settings WHERE setting_key = ?", (key,)
            ).fetchone()
            if existing is not None:
                continue
            conn.execute(
                """
                INSERT INTO daily_selection_settings (setting_key, setting_value, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (key, json.dumps(value, ensure_ascii=False), now, now),
            )
            seeded += 1
    if seeded:
        logger.info("初期応募目標設定・デイリー優先スコアの重みを登録しました: %d件", seeded)
    return seeded
