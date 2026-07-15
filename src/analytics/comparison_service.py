"""2つの期間のKPIを比較する。"""
from __future__ import annotations

import sqlite3

from src.analytics.kpi_service import compute_kpis

# 比較対象とする主要指標（すべて「大きいほど良い」と解釈する）
COMPARABLE_METRICS = [
    "application_count", "response_count", "response_rate", "interview_count", "interview_rate",
    "hired_count", "hired_rate", "contracted_count", "contract_amount_total", "contract_amount_avg",
]

METRIC_LABELS_JA = {
    "application_count": "応募数", "response_count": "返信数", "response_rate": "返信率",
    "interview_count": "面談数", "interview_rate": "面談率", "hired_count": "採用数",
    "hired_rate": "採用率", "contracted_count": "契約数", "contract_amount_total": "契約金額合計",
    "contract_amount_avg": "平均契約金額",
}


def compare_periods(conn: sqlite3.Connection, period_a: tuple[str, str], period_b: tuple[str, str]) -> dict:
    """期間A・期間BのKPIを比較する。各指標の差分・増減率・改善/悪化の分類を含む。"""
    kpi_a = compute_kpis(conn, *period_a)
    kpi_b = compute_kpis(conn, *period_b)

    diffs: dict[str, dict] = {}
    improved: list[str] = []
    worsened: list[str] = []
    for metric in COMPARABLE_METRICS:
        a_val, b_val = kpi_a.get(metric), kpi_b.get(metric)
        if a_val is None or b_val is None:
            diffs[metric] = {"a": a_val, "b": b_val, "diff": None, "pct_change": None}
            continue
        diff = a_val - b_val
        pct_change = round(diff / b_val * 100, 1) if b_val else None
        diffs[metric] = {"a": a_val, "b": b_val, "diff": diff, "pct_change": pct_change}
        label = METRIC_LABELS_JA.get(metric, metric)
        if diff > 0:
            improved.append(label)
        elif diff < 0:
            worsened.append(label)

    return {
        "period_a": {"date_from": period_a[0], "date_to": period_a[1], "kpi": kpi_a},
        "period_b": {"date_from": period_b[0], "date_to": period_b[1], "kpi": kpi_b},
        "diffs": diffs,
        "improved_metrics": improved,
        "worsened_metrics": worsened,
    }
