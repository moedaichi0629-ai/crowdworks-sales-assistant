"""分析結果・応募履歴データのCSV/Excel出力。

個人情報を含む出力（応募履歴・返信履歴 等）と、匿名化した分析用データ（将来のAI改善用）は
明確に分けて提供する。CSVはExcelで文字化けしないようUTF-8 (BOM付き) にする。
"""
from __future__ import annotations

import io
import sqlite3

import pandas as pd

from src.analytics.category_analytics import analyze_by_category_group, analyze_by_subcategory
from src.analytics.message_analytics import analyze_by_tone
from src.analytics.portfolio_analytics import analyze_by_portfolio
from src.repositories import (
    list_all_application_results,
    list_all_client_responses,
    list_application_analytics_base,
    list_daily_goals,
    list_interviews_with_job,
)
from src.utils import now_jst_str

# 将来のAI改善用データセットに含めてよい列（要件18: 個人情報・秘密情報は含めない）
ANONYMIZED_COLUMNS = [
    "job_category", "total_score_snapshot", "ai_score_snapshot", "safety_score_snapshot",
    "daily_priority_score_snapshot", "tone", "message_length", "portfolio_types",
    "proposed_price", "proposed_delivery_days", "applied_weekday", "applied_hour",
    "has_response", "has_interview", "is_hired", "contract_amount", "rejection_reason",
]


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    """Excelで文字化けしないよう UTF-8 (BOM付き) のCSVバイト列を生成する。"""
    return df.to_csv(index=False).encode("utf-8-sig")


def to_excel_bytes_multi(sheets: dict[str, pd.DataFrame]) -> bytes:
    """複数シートのExcel(.xlsx)バイト列を生成する。"""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, index=False, sheet_name=name[:31])
    return buffer.getvalue()


def _drop_json_columns(df: pd.DataFrame) -> pd.DataFrame:
    drop_cols = [c for c in df.columns if c.endswith("_json")]
    return df.drop(columns=drop_cols, errors="ignore")


def build_application_history_df(records: list[dict]) -> pd.DataFrame:
    """応募履歴の出力用DataFrame（個人情報を含む）。"""
    rows = []
    for r in records:
        job_snapshot = r.get("job_snapshot") or {}
        client_snapshot = r.get("client_snapshot") or {}
        rows.append({
            "record_id": r.get("id"), "job_id": r.get("job_id"), "案件タイトル": job_snapshot.get("title"),
            "応募日時": r.get("applied_at"), "応募経路": r.get("source_platform"),
            "契約種別": r.get("contract_type"), "応募金額": r.get("proposed_price"),
            "提案納期(日)": r.get("proposed_delivery_days"), "現在ステータス": r.get("application_status"),
            "営業文タイプ": r.get("tone"), "生成方式": r.get("generation_type"),
            "クライアント名": client_snapshot.get("client_name"), "クライアント評価": client_snapshot.get("client_rating"),
            "返信数": r.get("response_count"), "面談数": r.get("interview_count"),
            "結果": r.get("result_type"), "契約金額": r.get("contract_amount"),
        })
    return pd.DataFrame(rows)


def build_response_history_df(conn: sqlite3.Connection) -> pd.DataFrame:
    responses = list_all_client_responses(conn)
    df = pd.DataFrame(responses)
    return _drop_json_columns(df)


def build_interview_history_df(conn: sqlite3.Connection) -> pd.DataFrame:
    interviews = list_interviews_with_job(conn)
    df = pd.DataFrame(interviews)
    return _drop_json_columns(df)


def build_result_history_df(conn: sqlite3.Connection) -> pd.DataFrame:
    results = list_all_application_results(conn)
    df = pd.DataFrame(results)
    return _drop_json_columns(df)


def build_goal_history_df(conn: sqlite3.Connection) -> pd.DataFrame:
    from src.repositories import get_daily_application_counts

    goals = list_daily_goals(conn, limit=3650)
    applied_counts = get_daily_application_counts(conn)
    rows = []
    for g in goals:
        target_count = int(g.get("target_count", 0) or 0)
        applied = applied_counts.get(g["target_date"], 0)
        rows.append({
            "日付": g["target_date"], "目標数": target_count, "上限数": g.get("maximum_count"),
            "応募数": applied, "達成率(%)": round(applied / target_count * 100, 1) if target_count else None,
            "AI・開発目標": g.get("ai_development_target"), "デザイン目標": g.get("design_target"),
            "その他目標": g.get("other_target"),
        })
    return pd.DataFrame(rows)


def build_category_summary_df(records: list[dict]) -> pd.DataFrame:
    by_group = analyze_by_category_group(records)
    by_sub = analyze_by_subcategory(records)
    rows = []
    for name, stats in {**by_group, **by_sub}.items():
        rows.append({"分類": name, **stats})
    return pd.DataFrame(rows)


def build_tone_summary_df(records: list[dict]) -> pd.DataFrame:
    by_tone = analyze_by_tone(records)
    rows = [{"営業文タイプ": name, **stats} for name, stats in by_tone.items()]
    return pd.DataFrame(rows)


def build_portfolio_summary_df(conn: sqlite3.Connection, records: list[dict]) -> pd.DataFrame:
    by_portfolio = analyze_by_portfolio(conn, records)
    rows = []
    for name, stats in by_portfolio.items():
        row = dict(stats)
        row["used_categories"] = "、".join(row.get("used_categories") or [])
        rows.append({"ポートフォリオ": name, **row})
    return pd.DataFrame(rows)


def build_kpi_summary_df(kpis: dict) -> pd.DataFrame:
    labels = {
        "date_from": "期間(開始)", "date_to": "期間(終了)", "collected_count": "収集案件数",
        "analyzed_count": "AI分析済み案件数", "candidate_count": "応募候補数", "draft_count": "営業文作成数",
        "ready_count": "応募準備完了数", "application_count": "応募数", "response_count": "返信数",
        "response_rate": "返信率(%)", "interview_count": "面談数", "interview_rate": "面談率(%)",
        "hired_count": "採用数", "hired_rate": "採用率(%)", "contracted_count": "契約数",
        "contracted_rate": "契約率(%)", "rejected_count": "不採用数", "withdrawn_count": "辞退数",
        "unknown_count": "結果不明数", "contract_amount_total": "契約金額合計", "contract_amount_avg": "平均契約金額",
        "contract_amount_max": "最大契約金額", "contract_amount_min": "最小契約金額",
        "avg_hours_to_response": "応募から返信までの平均時間(h)", "avg_days_to_hire": "応募から採用までの平均日数",
    }
    rows = [{"指標": label, "値": kpis.get(key)} for key, label in labels.items() if key in kpis]
    return pd.DataFrame(rows)


def build_anonymized_dataset_df(records: list[dict]) -> pd.DataFrame:
    """将来のAI改善（第8段階）用に、個人情報・秘密情報を除外した分析用データセットを作る。

    クライアント名・本文中の個人情報・メールアドレス・電話番号・面談URL・詳細な返信本文・
    秘密情報は一切含めない（要件18）。
    """
    import datetime

    rows = []
    for r in records:
        job_snapshot = r.get("job_snapshot") or {}
        applied_at = r.get("applied_at")
        weekday, hour = None, None
        if applied_at:
            try:
                dt = datetime.datetime.strptime(str(applied_at)[:19], "%Y-%m-%d %H:%M:%S")
                weekday, hour = dt.weekday(), dt.hour
            except ValueError:
                pass

        rows.append({
            "job_category": job_snapshot.get("category"),
            "total_score_snapshot": r.get("total_score_snapshot"),
            "ai_score_snapshot": r.get("ai_score_snapshot"),
            "safety_score_snapshot": r.get("safety_score_snapshot"),
            "daily_priority_score_snapshot": r.get("daily_priority_score_snapshot"),
            "tone": r.get("tone"),
            "message_length": len(r["sent_message"]) if r.get("sent_message") else None,
            "portfolio_types": len(r.get("portfolio_snapshot") or []),
            "proposed_price": r.get("proposed_price"),
            "proposed_delivery_days": r.get("proposed_delivery_days"),
            "applied_weekday": weekday,
            "applied_hour": hour,
            "has_response": (r.get("response_count") or 0) > 0,
            "has_interview": (r.get("interview_count") or 0) > 0,
            "is_hired": r.get("result_type") == "採用",
            "contract_amount": r.get("contract_amount"),
            "rejection_reason": r.get("client_reason"),
        })
    df = pd.DataFrame(rows)
    missing = [c for c in ANONYMIZED_COLUMNS if c not in df.columns]
    for c in missing:
        df[c] = None
    return df[ANONYMIZED_COLUMNS] if not df.empty else pd.DataFrame(columns=ANONYMIZED_COLUMNS)
