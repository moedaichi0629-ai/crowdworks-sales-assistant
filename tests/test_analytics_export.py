"""CSV/Excel出力・匿名化データ(analytics_export)のテスト。"""
from __future__ import annotations

import io

import openpyxl
import pandas as pd

from src.analytics.analytics_export import (
    ANONYMIZED_COLUMNS,
    build_anonymized_dataset_df,
    build_application_history_df,
    to_csv_bytes,
    to_excel_bytes_multi,
)
from src.analytics.kpi_service import get_base_records
from src.analytics.period_service import PERIOD_ALL, resolve_period
from src.crm.application_history_service import create_application_history
from src.database import session
from src.repositories import insert_job, save_job_analysis


def _job(db_path) -> int:
    with session(db_path) as conn:
        job_id = insert_job(conn, {
            "title": "テスト案件", "body": "x" * 50, "source_type": "manual", "client_name": "個人情報テスト社",
        })
        save_job_analysis(conn, job_id, {
            "rule_based_score": 70, "ai_suitability_score": 80, "total_score": 80,
            "safety_score": 90, "risk_level": "low", "used_ai": 0,
        })
        return job_id


def _records(db_path) -> list[dict]:
    with session(db_path) as conn:
        d_from, d_to = resolve_period(PERIOD_ALL)
        return get_base_records(conn, d_from, d_to)


def test_csv_has_utf8_bom(db_path):
    job = _job(db_path)
    with session(db_path) as conn:
        create_application_history(conn, job)

    df = build_application_history_df(_records(db_path))
    csv_bytes = to_csv_bytes(df)
    assert csv_bytes.startswith(b"\xef\xbb\xbf")
    decoded = csv_bytes.decode("utf-8-sig")
    assert "テスト案件" in decoded


def test_excel_multi_sheet_output(db_path):
    df1 = pd.DataFrame([{"a": 1}])
    df2 = pd.DataFrame([{"b": 2}])
    xlsx_bytes = to_excel_bytes_multi({"シート1": df1, "シート2": df2})
    assert len(xlsx_bytes) > 0

    workbook = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    assert set(workbook.sheetnames) == {"シート1", "シート2"}


def test_anonymized_dataset_excludes_personal_info(db_path):
    job = _job(db_path)
    with session(db_path) as conn:
        create_application_history(conn, job)

    df = build_anonymized_dataset_df(_records(db_path))
    assert list(df.columns) == ANONYMIZED_COLUMNS
    forbidden_columns = {
        "client_name", "sent_message", "sent_short_message", "meeting_url",
        "client_snapshot", "job_snapshot", "portfolio_urls",
    }
    assert forbidden_columns.isdisjoint(set(df.columns))


def test_anonymized_dataset_row_count_matches_records(db_path):
    job = _job(db_path)
    with session(db_path) as conn:
        create_application_history(conn, job)

    df = build_anonymized_dataset_df(_records(db_path))
    assert len(df) == 1


def test_anonymized_dataset_empty_when_no_records():
    df = build_anonymized_dataset_df([])
    assert list(df.columns) == ANONYMIZED_COLUMNS
    assert len(df) == 0
