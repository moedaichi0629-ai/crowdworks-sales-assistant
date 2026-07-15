"""期間比較: 2つの期間のKPIを比較し、改善した指標・悪化した指標を確認する。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.analytics.comparison_service import METRIC_LABELS_JA, compare_periods
from src.analytics.period_service import PERIOD_CUSTOM, PERIOD_OPTIONS, previous_period, resolve_period
from src.database import init_db, session
from src.logger import get_logger

st.set_page_config(page_title="期間比較 | クラウドワークス案件管理ツール", page_icon="⚖️", layout="wide")
logger = get_logger()
init_db()

st.title("⚖️ 期間比較")
st.caption("2つの期間のKPIを比較します（例: 今週と先週、今月と先月、過去30日とその前30日）。")

st.markdown("#### 比較期間A")
ca1, ca2, ca3 = st.columns([2, 1, 1])
period_a = ca1.selectbox("期間A", options=PERIOD_OPTIONS, index=PERIOD_OPTIONS.index("今週"), key="period_a")
custom_a_from = custom_a_to = None
if period_a == PERIOD_CUSTOM:
    custom_a_from = ca2.date_input("開始日(A)").isoformat()
    custom_a_to = ca3.date_input("終了日(A)").isoformat()
date_a_from, date_a_to = resolve_period(period_a, custom_a_from, custom_a_to)

use_auto_b = st.checkbox("期間Bを「期間Aの直前の同じ長さの期間」に自動設定する", value=True)

if use_auto_b:
    date_b_from, date_b_to = previous_period(date_a_from, date_a_to)
    st.caption(f"期間B（自動設定）: {date_b_from} 〜 {date_b_to}")
else:
    st.markdown("#### 比較期間B")
    cb1, cb2, cb3 = st.columns([2, 1, 1])
    period_b = cb1.selectbox("期間B", options=PERIOD_OPTIONS, index=PERIOD_OPTIONS.index("先週"), key="period_b")
    custom_b_from = custom_b_to = None
    if period_b == PERIOD_CUSTOM:
        custom_b_from = cb2.date_input("開始日(B)").isoformat()
        custom_b_to = cb3.date_input("終了日(B)").isoformat()
    date_b_from, date_b_to = resolve_period(period_b, custom_b_from, custom_b_to)

st.caption(f"期間A: {date_a_from} 〜 {date_a_to} / 期間B: {date_b_from} 〜 {date_b_to}（日本時間）")

with session() as conn:
    comparison = compare_periods(conn, (date_a_from, date_a_to), (date_b_from, date_b_to))

st.divider()
st.subheader("📊 KPI差分")

rows = []
for metric, diff in comparison["diffs"].items():
    label = METRIC_LABELS_JA.get(metric, metric)
    rows.append({
        "指標": label, "期間A": diff["a"], "期間B": diff["b"], "差(A-B)": diff["diff"],
        "増減率": f"{diff['pct_change']}%" if diff["pct_change"] is not None else "-",
    })
st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

col_improved, col_worsened = st.columns(2)
with col_improved:
    st.markdown("#### ✅ 改善した指標（期間A > 期間B）")
    if comparison["improved_metrics"]:
        for m in comparison["improved_metrics"]:
            st.write(f"- {m}")
    else:
        st.write("該当する指標はありません。")

with col_worsened:
    st.markdown("#### ⚠️ 悪化した指標（期間A < 期間B）")
    if comparison["worsened_metrics"]:
        for m in comparison["worsened_metrics"]:
            st.write(f"- {m}")
    else:
        st.write("該当する指標はありません。")
