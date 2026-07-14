"""データベース初期化・案件登録更新・ステータス変更に関するテスト。"""
from __future__ import annotations

from src.config import STATUS_APPLIED, STATUS_CANDIDATE, STATUS_UNCONFIRMED
from src.database import session
from src.repositories import (
    get_job,
    update_favorite,
    update_memo,
    update_status_bulk,
    upsert_job,
)


def test_init_db_creates_tables(db_path):
    with session(db_path) as conn:
        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert {"jobs", "settings", "import_logs"}.issubset(tables)


def test_insert_new_job(db_path):
    with session(db_path) as conn:
        action, job_id = upsert_job(conn, {"title": "新規案件A", "url": "https://example.com/a"})
    assert action == "inserted"
    with session(db_path) as conn:
        job = get_job(conn, job_id)
    assert job["title"] == "新規案件A"
    assert job["status"] == STATUS_UNCONFIRMED


def test_update_existing_job_by_url(db_path):
    with session(db_path) as conn:
        _, job_id = upsert_job(conn, {"title": "案件B", "url": "https://example.com/b", "budget_text": "5万円"})

    with session(db_path) as conn:
        action, updated_id = upsert_job(
            conn, {"title": "案件B（更新後タイトル）", "url": "https://example.com/b", "budget_text": "10万円"}
        )

    assert action == "updated"
    assert updated_id == job_id
    with session(db_path) as conn:
        job = get_job(conn, job_id)
    assert job["budget_text"] == "10万円"


def test_user_input_fields_preserved_on_update(db_path):
    with session(db_path) as conn:
        _, job_id = upsert_job(conn, {"title": "案件C", "url": "https://example.com/c"})
        update_status_bulk(conn, [job_id], STATUS_CANDIDATE)
        update_favorite(conn, job_id, True)
        update_memo(conn, job_id, "重要なメモ")

    with session(db_path) as conn:
        upsert_job(conn, {"title": "案件C（本文変更）", "url": "https://example.com/c", "body": "新しい本文"})

    with session(db_path) as conn:
        job = get_job(conn, job_id)

    assert job["status"] == STATUS_CANDIDATE
    assert job["is_favorite"] == 1
    assert job["memo"] == "重要なメモ"
    assert job["body"] == "新しい本文"


def test_status_bulk_update(db_path):
    with session(db_path) as conn:
        _, id1 = upsert_job(conn, {"title": "案件D", "url": "https://example.com/d"})
        _, id2 = upsert_job(conn, {"title": "案件E", "url": "https://example.com/e"})
        count = update_status_bulk(conn, [id1, id2], STATUS_APPLIED)

    assert count == 2
    with session(db_path) as conn:
        job1 = get_job(conn, id1)
        job2 = get_job(conn, id2)
    assert job1["status"] == STATUS_APPLIED
    assert job2["status"] == STATUS_APPLIED
