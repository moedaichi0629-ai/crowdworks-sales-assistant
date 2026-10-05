"""手動入力・URLのみ一括登録(manual_import)のテスト。"""
from __future__ import annotations

from src.database import session
from src.manual_import import build_job_from_url_only, save_manual_job, save_url_only_jobs
from src.repositories import get_job, list_jobs
from src.validators import ValidationError


def test_build_job_from_url_only_generates_placeholder_title(db_path):
    data = build_job_from_url_only("https://crowdworks.jp/public/jobs/13308922?ref=recommend#x")
    assert data["title"] == "（タイトル未入力）13308922"
    assert data["url"] == "https://crowdworks.jp/public/jobs/13308922?ref=recommend#x"
    assert "案件一覧" in data["memo"]


def test_build_job_from_url_only_rejects_invalid_url():
    import pytest

    with pytest.raises(ValidationError):
        build_job_from_url_only("not-a-valid-url")


def test_save_url_only_jobs_inserts_new_stubs(db_path):
    with session(db_path) as conn:
        result = save_url_only_jobs(conn, [
            "https://crowdworks.jp/public/jobs/13308922",
            "https://crowdworks.jp/public/jobs/13296381",
        ])
    assert result == {"total": 2, "inserted": 2, "duplicate": 0, "errors": 0, "error_rows": []}

    with session(db_path) as conn:
        jobs = list_jobs(conn)
    assert len(jobs) == 2
    assert all(j["title"].startswith("（タイトル未入力）") for j in jobs)


def test_save_url_only_jobs_detects_duplicate_by_normalized_url(db_path):
    with session(db_path) as conn:
        save_url_only_jobs(conn, ["https://crowdworks.jp/public/jobs/13308922"])
        result = save_url_only_jobs(conn, ["https://crowdworks.jp/public/jobs/13308922?ref=recommend"])
    assert result == {"total": 1, "inserted": 0, "duplicate": 1, "errors": 0, "error_rows": []}

    with session(db_path) as conn:
        jobs = list_jobs(conn)
    assert len(jobs) == 1


def test_save_url_only_jobs_does_not_overwrite_existing_edited_job(db_path):
    """URL登録済み案件をユーザーが手動編集済みの場合、下書き一括登録で上書きしないこと。"""
    with session(db_path) as conn:
        _action, job_id = save_manual_job(conn, {
            "title": "本物のタイトル", "url": "https://crowdworks.jp/public/jobs/13308922",
            "body": "本物の本文です。",
        })

    with session(db_path) as conn:
        result = save_url_only_jobs(conn, ["https://crowdworks.jp/public/jobs/13308922"])
    assert result["duplicate"] == 1
    assert result["inserted"] == 0

    with session(db_path) as conn:
        job = get_job(conn, job_id)
    assert job["title"] == "本物のタイトル"
    assert job["body"] == "本物の本文です。"


def test_save_url_only_jobs_skips_blank_lines(db_path):
    with session(db_path) as conn:
        result = save_url_only_jobs(conn, ["", "   ", "https://crowdworks.jp/public/jobs/13308922"])
    assert result["total"] == 1
    assert result["inserted"] == 1


def test_save_url_only_jobs_reports_invalid_url_as_error(db_path):
    with session(db_path) as conn:
        result = save_url_only_jobs(conn, ["not-a-valid-url"])
    assert result["errors"] == 1
    assert result["inserted"] == 0
    assert result["error_rows"][0]["url"] == "not-a-valid-url"
