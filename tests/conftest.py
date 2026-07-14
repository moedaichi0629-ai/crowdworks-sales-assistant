"""pytest共通フィクスチャ。テストごとに独立した一時DBファイルを使用する。"""
from __future__ import annotations

import pytest

from src.database import init_db


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "test_jobs.db"
    init_db(path)
    return path
