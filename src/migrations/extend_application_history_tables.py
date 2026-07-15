"""第4段階Part2: 正式な応募履歴管理のためのテーブル拡張マイグレーション。

`application_records`（Part1で作成済み）へ、応募時点のスナップショット・応募後ステータス管理用の列を追加し、
新規テーブル application_status_history / client_responses / interviews / negotiation_records /
application_results / follow_up_tasks / application_timeline を作成する。

既存の jobs / job_analyses / application_drafts / application_versions / portfolios /
daily_application_goals / daily_candidates / application_records のデータは一切削除・変更しない
（列追加・新規テーブル作成のみ）。何度実行しても安全。
"""
from __future__ import annotations

from pathlib import Path

from src.config import DB_PATH
from src.logger import get_logger
from src.migrations.add_job_analysis_tables import _ensure_column, _table_exists

logger = get_logger()

# application_records へ追加する列（Part1時点では存在しない）
_APPLICATION_RECORD_NEW_COLUMNS = [
    ("application_version_id", "application_version_id INTEGER"),
    ("source_platform", "source_platform TEXT NOT NULL DEFAULT 'クラウドワークス'"),
    ("contract_type", "contract_type TEXT"),
    ("tax_type", "tax_type TEXT"),
    ("proposed_delivery_date", "proposed_delivery_date TEXT"),
    ("sent_message", "sent_message TEXT"),
    ("sent_short_message", "sent_short_message TEXT"),
    ("generation_type", "generation_type TEXT"),
    ("tone", "tone TEXT"),
    ("portfolio_snapshot_json", "portfolio_snapshot_json TEXT"),
    ("portfolio_urls_json", "portfolio_urls_json TEXT"),
    ("total_score_snapshot", "total_score_snapshot INTEGER"),
    ("ai_score_snapshot", "ai_score_snapshot INTEGER"),
    ("safety_score_snapshot", "safety_score_snapshot INTEGER"),
    ("daily_priority_score_snapshot", "daily_priority_score_snapshot INTEGER"),
    ("applicant_count_snapshot", "applicant_count_snapshot INTEGER"),
    ("client_snapshot_json", "client_snapshot_json TEXT"),
    ("job_snapshot_json", "job_snapshot_json TEXT"),
    ("current_response_status", "current_response_status TEXT NOT NULL DEFAULT '未読・確認待ち'"),
    ("next_action", "next_action TEXT"),
    ("next_action_due_at", "next_action_due_at TEXT"),
    # 応募記録は原則削除せず無効化する方式にするための列（要件16）
    ("is_active", "is_active INTEGER NOT NULL DEFAULT 1"),
    # 意図的な再応募の理由保存用（要件16）
    ("is_reapplication", "is_reapplication INTEGER NOT NULL DEFAULT 0"),
    ("reapplication_reason", "reapplication_reason TEXT"),
]

HISTORY_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS application_status_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_record_id INTEGER NOT NULL,
    previous_status TEXT,
    new_status TEXT NOT NULL,
    changed_at TEXT NOT NULL,
    change_reason TEXT,
    memo TEXT,
    FOREIGN KEY (application_record_id) REFERENCES application_records (id)
);

CREATE INDEX IF NOT EXISTS idx_status_history_record_id ON application_status_history (application_record_id);

CREATE TABLE IF NOT EXISTS client_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_record_id INTEGER NOT NULL,
    received_at TEXT NOT NULL,
    response_type TEXT,
    response_body TEXT,
    response_summary TEXT,
    questions_json TEXT,
    response_due_at TEXT,
    urgency TEXT,
    next_action TEXT,
    answer_body TEXT,
    answered_at TEXT,
    response_status TEXT NOT NULL DEFAULT '未対応',
    memo TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (application_record_id) REFERENCES application_records (id)
);

CREATE INDEX IF NOT EXISTS idx_client_responses_record_id ON client_responses (application_record_id);
CREATE INDEX IF NOT EXISTS idx_client_responses_due_at ON client_responses (response_due_at);

CREATE TABLE IF NOT EXISTS interviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_record_id INTEGER NOT NULL,
    title TEXT,
    scheduled_start TEXT,
    scheduled_end TEXT,
    timezone TEXT NOT NULL DEFAULT 'Asia/Tokyo',
    meeting_type TEXT,
    meeting_url TEXT,
    contact_name TEXT,
    preparation_notes TEXT,
    questions_json TEXT,
    self_intro_notes TEXT,
    proposal_notes TEXT,
    result TEXT,
    next_step TEXT,
    next_contact_due_at TEXT,
    interview_notes TEXT,
    status TEXT NOT NULL DEFAULT '調整中',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (application_record_id) REFERENCES application_records (id)
);

CREATE INDEX IF NOT EXISTS idx_interviews_record_id ON interviews (application_record_id);
CREATE INDEX IF NOT EXISTS idx_interviews_scheduled_start ON interviews (scheduled_start);

CREATE TABLE IF NOT EXISTS negotiation_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_record_id INTEGER NOT NULL,
    original_price INTEGER,
    client_offered_price INTEGER,
    agreed_price INTEGER,
    original_delivery_date TEXT,
    requested_delivery_date TEXT,
    agreed_delivery_date TEXT,
    revision_count INTEGER,
    deliverables_json TEXT,
    payment_terms TEXT,
    external_cost_terms TEXT,
    maintenance_terms TEXT,
    additional_work_json TEXT,
    agreement_status TEXT NOT NULL DEFAULT '未確認',
    memo TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (application_record_id) REFERENCES application_records (id)
);

CREATE INDEX IF NOT EXISTS idx_negotiation_records_record_id ON negotiation_records (application_record_id);

CREATE TABLE IF NOT EXISTS application_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_record_id INTEGER NOT NULL,
    result_type TEXT NOT NULL,
    result_date TEXT,
    hired_at TEXT,
    contracted_at TEXT,
    contract_amount INTEGER,
    contract_type TEXT,
    contract_start_date TEXT,
    contract_end_date TEXT,
    planned_delivery_date TEXT,
    actual_delivery_date TEXT,
    client_reason TEXT,
    inferred_reason TEXT,
    improvement_points_json TEXT,
    client_comment TEXT,
    continuation_possible TEXT,
    is_recurring INTEGER NOT NULL DEFAULT 0,
    withdrawal_reason TEXT,
    memo TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (application_record_id) REFERENCES application_records (id)
);

CREATE INDEX IF NOT EXISTS idx_application_results_record_id ON application_results (application_record_id);

CREATE TABLE IF NOT EXISTS follow_up_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_record_id INTEGER NOT NULL,
    due_at TEXT NOT NULL,
    task_type TEXT,
    task_content TEXT,
    status TEXT NOT NULL DEFAULT '未対応',
    completed_at TEXT,
    memo TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (application_record_id) REFERENCES application_records (id)
);

CREATE INDEX IF NOT EXISTS idx_follow_up_tasks_record_id ON follow_up_tasks (application_record_id);
CREATE INDEX IF NOT EXISTS idx_follow_up_tasks_due_at ON follow_up_tasks (due_at);

CREATE TABLE IF NOT EXISTS application_timeline (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_record_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    event_at TEXT NOT NULL,
    event_title TEXT,
    event_detail TEXT,
    related_table TEXT,
    related_id INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY (application_record_id) REFERENCES application_records (id)
);

CREATE INDEX IF NOT EXISTS idx_application_timeline_record_id ON application_timeline (application_record_id);
CREATE INDEX IF NOT EXISTS idx_application_timeline_event_at ON application_timeline (event_at);
"""


def run_migration(db_path: Path | str = DB_PATH) -> dict:
    """応募履歴管理用の列・テーブルを追加する。複数回実行しても安全。

    既存の application_records データ（Part1で作成済みの行）は一切削除・変更しない
    （列追加のみ。新規列は安全な既定値で埋まる）。
    """
    from src.database import session  # 循環importを避けるため関数内でimport

    with session(db_path) as conn:
        already_had_history_tables = _table_exists(conn, "application_status_history")
        if _table_exists(conn, "application_records"):
            for column_name, column_def in _APPLICATION_RECORD_NEW_COLUMNS:
                _ensure_column(conn, "application_records", column_name, column_def)
        conn.executescript(HISTORY_SCHEMA_SQL)

    logger.info("データベースマイグレーションを実行しました: extend_application_history_tables")

    return {"tables_created": not already_had_history_tables}
