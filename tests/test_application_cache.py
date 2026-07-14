"""営業文生成キャッシュ(application_cache)のテスト。"""
from __future__ import annotations

from src.application.application_cache import compute_content_hash, get_cached_draft
from src.database import session
from src.repositories import create_application_draft, insert_job

_JOB = {"title": "案件タイトル", "body": "案件本文です。", "budget_text": "10000円", "deadline": "2026-08-01"}


def _hash(**overrides):
    kwargs = dict(
        job=_JOB, analysis_summary=None, profile_updated_at="2026-01-01 00:00:00", profile_version=1,
        selected_portfolio_ids=[1, 2], generation_type="ai", tone="標準", length_type="標準",
        proposed_price=10000, proposed_delivery_days=7, additional_message=None, exclude_content=None,
        prompt_version="v1", provider="openai", model="gpt-4o-mini",
    )
    kwargs.update(overrides)
    return compute_content_hash(**kwargs)


def test_same_inputs_produce_same_hash():
    assert _hash() == _hash()


def test_different_job_body_changes_hash():
    other_job = {**_JOB, "body": "別の本文です。"}
    assert _hash() != _hash(job=other_job)


def test_different_tone_changes_hash():
    assert _hash() != _hash(tone="丁寧")


def test_different_portfolio_selection_changes_hash():
    assert _hash() != _hash(selected_portfolio_ids=[3])


def test_portfolio_selection_order_independent():
    # 選択順ではなく、選択集合自体が同じならハッシュも同じ（sorted済み）
    assert _hash(selected_portfolio_ids=[1, 2]) == _hash(selected_portfolio_ids=[2, 1])


def test_profile_version_change_invalidates_cache():
    assert _hash(profile_version=1) != _hash(profile_version=2)


def test_get_cached_draft_returns_none_when_absent(db_path):
    with session(db_path) as conn:
        job_id = insert_job(conn, {"title": "テスト案件", "source_type": "manual"})
    with session(db_path) as conn:
        cached = get_cached_draft(conn, job_id, "nonexistent-hash")
    assert cached is None


def test_get_cached_draft_returns_latest_matching_row(db_path):
    with session(db_path) as conn:
        job_id = insert_job(conn, {"title": "テスト案件", "source_type": "manual"})
        create_application_draft(conn, job_id, {"application_message": "本文", "source_hash": "hash-a"})
    with session(db_path) as conn:
        cached = get_cached_draft(conn, job_id, "hash-a")
    assert cached is not None
    assert cached["application_message"] == "本文"
