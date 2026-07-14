"""CSVインポート機能のテスト。"""
from __future__ import annotations

import pandas as pd

from src.csv_import import auto_map_columns, import_dataframe, read_csv_bytes
from src.database import session
from src.validators import ValidationError
import pytest


def test_auto_map_columns_japanese_headers():
    mapping, unmapped = auto_map_columns(["案件タイトル", "案件URL", "予算", "クライアント名"])
    assert mapping["title"] == "案件タイトル"
    assert mapping["url"] == "案件URL"
    assert mapping["budget"] == "予算"
    assert mapping["client_name"] == "クライアント名"


def test_auto_map_columns_english_headers():
    mapping, _ = auto_map_columns(["title", "url", "budget_min", "budget_max"])
    assert mapping["title"] == "title"
    assert mapping["budget_min"] == "budget_min"


def test_read_csv_bytes_utf8_sig():
    content = "案件タイトル,案件URL\nテスト案件,https://example.com/1\n".encode("utf-8-sig")
    df = read_csv_bytes(content, "sample.csv")
    assert len(df) == 1
    assert df.iloc[0]["案件タイトル"] == "テスト案件"


def test_read_csv_bytes_rejects_non_csv_extension():
    with pytest.raises(ValidationError):
        read_csv_bytes(b"data", "sample.txt")


def test_import_dataframe_inserts_new_rows(db_path):
    df = pd.DataFrame(
        {"案件タイトル": ["案件A", "案件B"], "案件URL": ["https://example.com/a", "https://example.com/b"]}
    )
    mapping, _ = auto_map_columns(list(df.columns))
    with session(db_path) as conn:
        result = import_dataframe(conn, df, mapping, source_name="test.csv")
    assert result["total"] == 2
    assert result["inserted"] == 2
    assert result["errors"] == 0


def test_import_dataframe_detects_duplicate_on_second_import(db_path):
    df = pd.DataFrame({"案件タイトル": ["案件C"], "案件URL": ["https://example.com/c"]})
    mapping, _ = auto_map_columns(list(df.columns))
    with session(db_path) as conn:
        import_dataframe(conn, df, mapping, source_name="test.csv")
        result = import_dataframe(conn, df, mapping, source_name="test.csv")
    assert result["duplicate"] == 1
    assert result["inserted"] == 0


def test_import_dataframe_reports_error_for_missing_title(db_path):
    df = pd.DataFrame({"案件タイトル": [None], "案件URL": ["https://example.com/d"]})
    mapping, _ = auto_map_columns(list(df.columns))
    with session(db_path) as conn:
        result = import_dataframe(conn, df, mapping, source_name="test.csv")
    assert result["errors"] == 1
    assert result["inserted"] == 0
    assert len(result["error_rows"]) == 1
