"""重複判定(duplicate_checker)とURL正規化(utils.normalize_url)のテスト。"""
from __future__ import annotations

from src.database import session
from src.duplicate_checker import find_duplicate
from src.repositories import upsert_job
from src.utils import normalize_url


def test_normalize_url_ignores_query_and_trailing_slash():
    a = normalize_url("https://example.com/jobs/123/?ref=abc")
    b = normalize_url("https://example.com/jobs/123")
    assert a == b


def test_normalize_url_case_insensitive_scheme_and_host():
    a = normalize_url("HTTPS://Example.com/jobs/123")
    b = normalize_url("https://example.com/jobs/123")
    assert a == b


def test_find_duplicate_by_external_job_id(db_path):
    with session(db_path) as conn:
        upsert_job(conn, {"title": "案件X", "external_job_id": "EXT-1", "url": "https://a.example.com/1"})
        dup = find_duplicate(conn, {"title": "別タイトル", "external_job_id": "EXT-1"})
    assert dup is not None
    assert dup["external_job_id"] == "EXT-1"


def test_find_duplicate_by_normalized_url(db_path):
    with session(db_path) as conn:
        upsert_job(conn, {"title": "案件Y", "url": "https://a.example.com/jobs/2"})
        dup = find_duplicate(
            conn, {"title": "別タイトル", "normalized_url": normalize_url("https://a.example.com/jobs/2/?x=1")}
        )
    assert dup is not None
    assert dup["title"] == "案件Y"


def test_find_duplicate_by_title_and_client(db_path):
    with session(db_path) as conn:
        upsert_job(conn, {"title": "案件Z", "client_name": "株式会社サンプル"})
        dup = find_duplicate(conn, {"title": "案件Z", "client_name": "株式会社サンプル"})
    assert dup is not None


def test_find_duplicate_by_body_similarity(db_path):
    body = "これはテスト用の非常に長い案件本文です。" * 5
    with session(db_path) as conn:
        upsert_job(conn, {"title": "案件W", "body": body})
        dup = find_duplicate(conn, {"title": "案件W", "body": body})
    assert dup is not None


def test_no_duplicate_for_unrelated_job(db_path):
    with session(db_path) as conn:
        upsert_job(conn, {"title": "案件V", "url": "https://a.example.com/v"})
        dup = find_duplicate(conn, {"title": "全く別の案件", "url": "https://b.example.com/other"})
    assert dup is None
