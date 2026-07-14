"""第3段階: 営業文自動生成機能のためのテーブルを追加するマイグレーション。

新規テーブル: application_drafts / application_versions / application_templates /
pricing_settings / application_checklists / portfolio_matches。
既存の portfolios テーブルにはポートフォリオ分類用の列を追加する。

既存の jobs / settings / import_logs / job_analyses / user_profiles / skills /
portfolios / analysis_settings のデータは一切削除・変更しない
（列追加のみ・新規行の追加のみ）。何度実行しても安全。
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from src.config import DB_PATH
from src.logger import get_logger
from src.migrations.add_job_analysis_tables import _ensure_column, _table_exists

logger = get_logger()

APPLICATION_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS application_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    analysis_id INTEGER,
    profile_id INTEGER,
    title TEXT,
    generation_type TEXT,
    tone TEXT,
    length_type TEXT,
    application_message TEXT,
    short_message TEXT,
    proposed_price INTEGER,
    minimum_price INTEGER,
    ideal_price INTEGER,
    price_reason TEXT,
    proposed_delivery_days INTEGER,
    minimum_delivery_days INTEGER,
    safe_delivery_days INTEGER,
    delivery_reason TEXT,
    questions_for_client_json TEXT,
    client_questions_json TEXT,
    client_answers_json TEXT,
    selected_portfolio_ids_json TEXT,
    portfolio_reasons_json TEXT,
    skills_to_highlight_json TEXT,
    proposed_approach_json TEXT,
    warnings_json TEXT,
    missing_information_json TEXT,
    confidence_score INTEGER,
    preparation_status TEXT NOT NULL DEFAULT '未作成',
    user_memo TEXT,
    provider TEXT,
    model TEXT,
    prompt_version TEXT,
    source_hash TEXT,
    copied_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_application_drafts_job_id ON application_drafts (job_id);
CREATE INDEX IF NOT EXISTS idx_application_drafts_source_hash ON application_drafts (source_hash);
CREATE INDEX IF NOT EXISTS idx_application_drafts_created_at ON application_drafts (created_at);

CREATE TABLE IF NOT EXISTS application_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_draft_id INTEGER NOT NULL,
    version_number INTEGER NOT NULL,
    version_type TEXT,
    application_message TEXT,
    short_message TEXT,
    change_instruction TEXT,
    created_by TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_application_versions_draft_id ON application_versions (application_draft_id);

CREATE TABLE IF NOT EXISTS application_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_name TEXT NOT NULL,
    category TEXT,
    tone TEXT,
    length_type TEXT,
    template_body TEXT,
    is_default INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pricing_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    setting_key TEXT NOT NULL UNIQUE,
    setting_value TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS application_checklists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_draft_id INTEGER NOT NULL UNIQUE,
    job_reviewed INTEGER NOT NULL DEFAULT 0,
    conditions_confirmed INTEGER NOT NULL DEFAULT 0,
    price_confirmed INTEGER NOT NULL DEFAULT 0,
    deadline_confirmed INTEGER NOT NULL DEFAULT 0,
    message_confirmed INTEGER NOT NULL DEFAULT 0,
    portfolio_confirmed INTEGER NOT NULL DEFAULT 0,
    client_questions_answered INTEGER NOT NULL DEFAULT 0,
    safety_confirmed INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolio_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    portfolio_id INTEGER NOT NULL,
    relevance_score INTEGER NOT NULL DEFAULT 0,
    matched_skills_json TEXT,
    matched_category TEXT,
    match_reason TEXT,
    is_selected INTEGER NOT NULL DEFAULT 0,
    selection_order INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_portfolio_matches_job_id ON portfolio_matches (job_id);
"""

# portfolios テーブルへ追加する列（第2段階時点では存在しない）
_PORTFOLIO_NEW_COLUMNS = [
    ("portfolio_type", "portfolio_type TEXT"),
    ("main_category", "main_category TEXT"),
    ("subcategories_json", "subcategories_json TEXT"),
    ("target_job_categories_json", "target_job_categories_json TEXT"),
    ("design_tools_json", "design_tools_json TEXT"),
    ("technology_keywords_json", "technology_keywords_json TEXT"),
    ("sales_description", "sales_description TEXT"),
    ("priority", "priority INTEGER NOT NULL DEFAULT 50"),
    ("for_development", "for_development INTEGER NOT NULL DEFAULT 1"),
    ("for_design", "for_design INTEGER NOT NULL DEFAULT 0"),
    ("for_ai_design", "for_ai_design INTEGER NOT NULL DEFAULT 0"),
    ("display_order", "display_order INTEGER NOT NULL DEFAULT 50"),
]


def run_migration(db_path: Path | str = DB_PATH) -> dict:
    """営業文自動生成機能用テーブルを作成し、ポートフォリオ列を追加、初期データを投入する。

    複数回実行しても安全。既存の jobs/job_analyses/user_profiles/skills/portfolios/
    analysis_settings データは変更・削除しない（列追加・不足分の新規追加のみ）。
    """
    from src.database import session  # 循環importを避けるため関数内でimport

    with session(db_path) as conn:
        already_had_tables = _table_exists(conn, "application_drafts")
        conn.executescript(APPLICATION_SCHEMA_SQL)
        if _table_exists(conn, "portfolios"):
            for column_name, column_def in _PORTFOLIO_NEW_COLUMNS:
                _ensure_column(conn, "portfolios", column_name, column_def)

    logger.info("データベースマイグレーションを実行しました: add_application_draft_tables")

    portfolios_enriched = _enrich_and_seed_portfolios(db_path)
    templates_seeded = _seed_default_templates_if_absent(db_path)
    pricing_seeded = _seed_default_pricing_settings_if_absent(db_path)

    return {
        "tables_created": not already_had_tables,
        "portfolios_enriched": portfolios_enriched,
        "templates_seeded": templates_seeded,
        "pricing_seeded": pricing_seeded,
    }


def _enrich_and_seed_portfolios(db_path: Path | str) -> int:
    """既存ポートフォリオの空欄項目を補完し、未登録の初期ポートフォリオ（AI・開発/デザイン/GitHub）を追加する。

    タイトルが完全一致する行が既に存在する場合は重複登録せず、
    空欄（NULL・空文字・空リスト）の列のみ補完する。ユーザーが既に入力した値は上書きしない。
    """
    from src.database import session
    from src.portfolio.default_portfolios import EXISTING_PORTFOLIO_ENRICHMENT, NEW_DEFAULT_PORTFOLIOS
    from src.utils import now_jst_str

    changed = 0
    with session(db_path) as conn:
        profile_row = conn.execute(
            "SELECT id FROM user_profiles WHERE profile_name = 'default'"
        ).fetchone()
        if profile_row is None:
            return 0
        profile_id = profile_row["id"]

        now = now_jst_str()

        for title, enrichment in EXISTING_PORTFOLIO_ENRICHMENT.items():
            row = conn.execute(
                "SELECT * FROM portfolios WHERE profile_id = ? AND title = ?", (profile_id, title)
            ).fetchone()
            if row is None:
                continue
            updates: dict = {}
            for key, value in enrichment.items():
                column = f"{key}_json" if isinstance(value, list) else key
                if column not in row.keys():
                    continue
                current = row[column]
                is_empty = current is None or current == "" or current == "[]"
                if not is_empty:
                    continue
                updates[column] = json.dumps(value, ensure_ascii=False) if isinstance(value, list) else value
            if updates:
                set_clause = ", ".join(f"{c} = ?" for c in updates) + ", updated_at = ?"
                conn.execute(
                    f"UPDATE portfolios SET {set_clause} WHERE id = ?",
                    [*updates.values(), now, row["id"]],
                )
                changed += 1

        for portfolio in NEW_DEFAULT_PORTFOLIOS:
            existing = conn.execute(
                "SELECT id FROM portfolios WHERE profile_id = ? AND title = ?",
                (profile_id, portfolio["title"]),
            ).fetchone()
            if existing is not None:
                continue
            conn.execute(
                """
                INSERT INTO portfolios
                    (profile_id, title, description, technologies_json, skills_json,
                     portfolio_url, github_url, is_active,
                     portfolio_type, main_category, subcategories_json, target_job_categories_json,
                     design_tools_json, technology_keywords_json, sales_description, priority,
                     for_development, for_design, for_ai_design, display_order,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile_id, portfolio["title"], portfolio.get("description"),
                    json.dumps(portfolio.get("technologies", []), ensure_ascii=False),
                    json.dumps(portfolio.get("skills", []), ensure_ascii=False),
                    portfolio.get("portfolio_url"), portfolio.get("github_url"),
                    portfolio.get("portfolio_type"), portfolio.get("main_category"),
                    json.dumps(portfolio.get("subcategories", []), ensure_ascii=False),
                    json.dumps(portfolio.get("target_job_categories", []), ensure_ascii=False),
                    json.dumps(portfolio.get("design_tools", []), ensure_ascii=False),
                    json.dumps(portfolio.get("technology_keywords", []), ensure_ascii=False),
                    portfolio.get("sales_description"), portfolio.get("priority", 50),
                    int(portfolio.get("for_development", True)), int(portfolio.get("for_design", False)),
                    int(portfolio.get("for_ai_design", False)), portfolio.get("display_order", 50),
                    now, now,
                ),
            )
            changed += 1

    if changed:
        logger.info("ポートフォリオの初期分類情報を登録・補完しました: %d件", changed)
    return changed


def _seed_default_templates_if_absent(db_path: Path | str) -> int:
    from src.application.template_generator import DEFAULT_TEMPLATE_DEFINITIONS
    from src.database import session
    from src.utils import now_jst_str

    seeded = 0
    now = now_jst_str()
    with session(db_path) as conn:
        for template in DEFAULT_TEMPLATE_DEFINITIONS:
            existing = conn.execute(
                "SELECT id FROM application_templates WHERE template_name = ?",
                (template["template_name"],),
            ).fetchone()
            if existing is not None:
                continue
            conn.execute(
                """
                INSERT INTO application_templates
                    (template_name, category, tone, length_type, template_body, is_default, is_active,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 1, 1, ?, ?)
                """,
                (
                    template["template_name"], template["category"], template.get("tone"),
                    template.get("length_type"), template["template_body"], now, now,
                ),
            )
            seeded += 1
    if seeded:
        logger.info("初期営業文テンプレートを登録しました: %d件", seeded)
    return seeded


def _seed_default_pricing_settings_if_absent(db_path: Path | str) -> int:
    from src.config import DEFAULT_DELIVERY_SETTINGS, DEFAULT_PRICING_SETTINGS
    from src.database import session
    from src.utils import now_jst_str

    seeded = 0
    now = now_jst_str()
    all_defaults = {
        f"pricing.{k}": v for k, v in DEFAULT_PRICING_SETTINGS.items()
    }
    all_defaults.update({f"delivery.{k}": v for k, v in DEFAULT_DELIVERY_SETTINGS.items()})

    with session(db_path) as conn:
        for key, value in all_defaults.items():
            existing = conn.execute(
                "SELECT id FROM pricing_settings WHERE setting_key = ?", (key,)
            ).fetchone()
            if existing is not None:
                continue
            conn.execute(
                """
                INSERT INTO pricing_settings (setting_key, setting_value, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (key, json.dumps(value, ensure_ascii=False), now, now),
            )
            seeded += 1
    if seeded:
        logger.info("初期料金・納期設定を登録しました: %d件", seeded)
    return seeded
