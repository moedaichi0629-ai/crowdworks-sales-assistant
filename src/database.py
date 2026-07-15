"""SQLiteデータベースの接続・初期化を担当するモジュール。"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from src.config import DB_PATH
from src.logger import get_logger

logger = get_logger()

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_job_id TEXT,
    title TEXT NOT NULL,
    url TEXT,
    normalized_url TEXT,
    description TEXT,
    body TEXT,
    job_type TEXT,
    category TEXT,
    budget_min INTEGER,
    budget_max INTEGER,
    budget_text TEXT,
    hourly_rate TEXT,
    published_at TEXT,
    deadline TEXT,
    applicant_count INTEGER,
    recruitment_count INTEGER,
    client_name TEXT,
    client_rating REAL,
    client_review_count INTEGER,
    identity_verified INTEGER,
    rule_check_verified INTEGER,
    matched_keyword TEXT,
    excluded_keyword TEXT,
    source_type TEXT,
    status TEXT NOT NULL DEFAULT '未確認',
    is_favorite INTEGER NOT NULL DEFAULT 0,
    memo TEXT,
    collected_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_normalized_url ON jobs (normalized_url);
CREATE INDEX IF NOT EXISTS idx_jobs_external_job_id ON jobs (external_job_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status);
CREATE INDEX IF NOT EXISTS idx_jobs_collected_at ON jobs (collected_at);

CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    setting_key TEXT NOT NULL UNIQUE,
    setting_value TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS import_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT,
    source_name TEXT,
    total_count INTEGER DEFAULT 0,
    inserted_count INTEGER DEFAULT 0,
    updated_count INTEGER DEFAULT 0,
    duplicate_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    error_detail TEXT,
    created_at TEXT NOT NULL
);
"""


def get_connection(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    """SQLite接続を取得する（行をdict風に扱えるようRow設定済み）。"""
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def session(db_path: Path | str = DB_PATH) -> Iterator[sqlite3.Connection]:
    """with文で使うDBセッション。正常終了時はcommit、例外時はrollbackする。"""
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path | str = DB_PATH) -> None:
    """テーブルが存在しない場合に作成する。初回起動時に自動実行される。

    第2段階のAI案件分析用テーブル追加マイグレーションも合わせて実行する
    （何度実行しても安全で、既存データは変更・削除しない）。
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with session(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
    logger.info("データベースを初期化しました: %s", db_path)

    from src.migrations.add_job_analysis_tables import run_migration as run_analysis_migration
    from src.migrations.add_application_draft_tables import run_migration as run_application_migration
    from src.migrations.add_daily_application_tables import run_migration as run_daily_migration
    from src.migrations.extend_application_history_tables import run_migration as run_history_migration

    run_analysis_migration(db_path)
    run_application_migration(db_path)
    run_daily_migration(db_path)
    run_history_migration(db_path)
