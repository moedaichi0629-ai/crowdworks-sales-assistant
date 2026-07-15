"""第4段階Part2: 応募履歴管理テーブル拡張マイグレーションのテスト。"""
from __future__ import annotations

import sqlite3

import pytest

from src.database import init_db, session
from src.repositories import create_application_record, insert_job


def test_migration_creates_new_tables(db_path):
    with session(db_path) as conn:
        tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    expected = {
        "application_status_history", "client_responses", "interviews",
        "negotiation_records", "application_results", "follow_up_tasks", "application_timeline",
    }
    assert expected.issubset(tables)


def test_migration_is_idempotent(db_path):
    init_db(db_path)
    init_db(db_path)  # 例外が発生しないこと


def test_application_records_has_new_columns(db_path):
    with session(db_path) as conn:
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(application_records)")}
    expected = {
        "source_platform", "contract_type", "tax_type", "proposed_delivery_date", "sent_message",
        "sent_short_message", "generation_type", "tone", "portfolio_snapshot_json", "portfolio_urls_json",
        "total_score_snapshot", "ai_score_snapshot", "safety_score_snapshot", "daily_priority_score_snapshot",
        "applicant_count_snapshot", "client_snapshot_json", "job_snapshot_json", "current_response_status",
        "next_action", "next_action_due_at", "is_active", "is_reapplication", "reapplication_reason",
    }
    assert expected.issubset(columns)


def test_existing_application_records_preserved_across_migration(db_path):
    with session(db_path) as conn:
        job_id = insert_job(conn, {"title": "既存応募案件", "source_type": "manual"})
        create_application_record(conn, {"job_id": job_id, "proposed_price": 20000})

    init_db(db_path)  # マイグレーションを再実行

    with session(db_path) as conn:
        rows = conn.execute("SELECT proposed_price FROM application_records WHERE job_id = ?", (job_id,)).fetchall()
    assert any(r["proposed_price"] == 20000 for r in rows)


def test_foreign_key_integrity_enforced(db_path):
    """application_record_id が存在しない子テーブル行の挿入は外部キー制約で拒否される。"""
    with session(db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO client_responses
                    (application_record_id, received_at, response_status, created_at, updated_at)
                VALUES (999999, '2026-07-15 10:00:00', '未対応', '2026-07-15 10:00:00', '2026-07-15 10:00:00')
                """
            )
