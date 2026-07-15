"""営業成績ダッシュボード: KPI・目標達成率・ジャンル別/営業文別/ポートフォリオ別/スコア帯別の成果、
改善候補、データ品質をまとめて確認する。
"""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from src.analytics.category_analytics import analyze_by_category_group
from src.analytics.data_quality_service import check_data_quality
from src.analytics.goal_analytics import analyze_goal_achievement
from src.analytics.insight_service import generate_insights
from src.analytics.kpi_service import build_daily_trend, compute_kpis, get_base_records
from src.analytics.message_analytics import analyze_by_tone
from src.analytics.period_service import PERIOD_CUSTOM, PERIOD_OPTIONS, PERIOD_THIS_MONTH, resolve_period
from src.analytics.portfolio_analytics import analyze_by_portfolio
from src.analytics.score_analytics import analyze_by_total_score
from src.analytics.timing_analytics import analyze_by_weekday
from src.database import init_db, session
from src.logger import get_logger
from src.repositories import list_jobs_with_analysis_for_scoring

st.set_page_config(page_title="営業成績ダッシュボード | クラウドワークス案件管理ツール", page_icon="📊", layout="wide")
logger = get_logger()
init_db()

st.title("📊 営業成績ダッシュボード")
st.caption("応募〜返信〜面談〜採用までの成果を集計します。分析結果を自動でAI学習へ反映する機能は含みません。")

col_period, col_from, col_to = st.columns([2, 1, 1])
period = col_period.selectbox("期間", options=PERIOD_OPTIONS, index=PERIOD_OPTIONS.index(PERIOD_THIS_MONTH))
custom_from = custom_to = None
if period == PERIOD_CUSTOM:
    custom_from = col_from.date_input("開始日").isoformat()
    custom_to = col_to.date_input("終了日").isoformat()

date_from, date_to = resolve_period(period, custom_from, custom_to)
st.caption(f"集計期間: {date_from} 〜 {date_to}（日本時間）")

with session() as conn:
    kpis = compute_kpis(conn, date_from, date_to)
    records = get_base_records(conn, date_from, date_to)
    goal_stats = analyze_goal_achievement(conn, date_from, date_to)
    insights = generate_insights(conn, date_from, date_to)
    quality = check_data_quality(records)
    jobs_for_scoring = list_jobs_with_analysis_for_scoring(conn)

# ============================= KPIカード =============================
st.subheader("📈 KPIサマリー")
k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("応募数", kpis["application_count"])
k2.metric("返信率", f"{kpis['response_rate']}%" if kpis["response_rate"] is not None else "-")
k3.metric("面談率", f"{kpis['interview_rate']}%" if kpis["interview_rate"] is not None else "-")
k4.metric("採用率", f"{kpis['hired_rate']}%" if kpis["hired_rate"] is not None else "-")
k5.metric("契約金額合計", f"{kpis['contract_amount_total']:,}円" if kpis["contract_amount_total"] is not None else "-")
k6.metric("目標達成率", f"{goal_stats['achievement_rate']}%" if goal_stats["achievement_rate"] is not None else "-")

with st.expander("パイプライン全体の件数（収集〜応募）"):
    p1, p2, p3, p4, p5 = st.columns(5)
    p1.metric("収集案件数", kpis["collected_count"])
    p2.metric("AI分析済み案件数", kpis["analyzed_count"])
    p3.metric("応募候補数", kpis["candidate_count"])
    p4.metric("営業文作成数", kpis["draft_count"])
    p5.metric("応募準備完了数", kpis["ready_count"])

    q1, q2, q3, q4 = st.columns(4)
    q1.metric("契約数", kpis["contracted_count"])
    q2.metric("不採用数", kpis["rejected_count"])
    q3.metric("辞退数", kpis["withdrawn_count"])
    q4.metric("結果不明数", kpis["unknown_count"])

    avg_amount_text = f"{kpis['contract_amount_avg']:,}円" if kpis["contract_amount_avg"] is not None else "-"
    avg_hours_text = f"{kpis['avg_hours_to_response']}時間" if kpis["avg_hours_to_response"] is not None else "-"
    st.caption(f"平均契約金額: {avg_amount_text} / 応募から返信までの平均時間: {avg_hours_text}")

st.divider()

# ============================= グラフ =============================
st.subheader("📉 推移・内訳グラフ")

trend = build_daily_trend(records)
if trend:
    trend_df = pd.DataFrame(trend)
    g1, g2 = st.columns(2)
    with g1:
        st.caption("日別応募数")
        chart = alt.Chart(trend_df).mark_bar(color="#4C78A8").encode(x="date:O", y="応募数:Q")
        st.altair_chart(chart, width="stretch")
    with g2:
        st.caption("日別返信・採用数")
        melted = trend_df.melt(id_vars="date", value_vars=["返信数", "採用数"], var_name="種別", value_name="件数")
        chart = alt.Chart(melted).mark_bar().encode(x="date:O", y="件数:Q", color="種別:N")
        st.altair_chart(chart, width="stretch")

    st.caption("契約金額推移")
    chart = alt.Chart(trend_df).mark_bar(color="#54A24B").encode(x="date:O", y="契約金額:Q")
    st.altair_chart(chart, width="stretch")
else:
    st.info("この期間の応募データがまだありません。")

g3, g4 = st.columns(2)
with g3:
    st.caption("ジャンル別成果（応募数）")
    by_group = analyze_by_category_group(records)
    group_df = pd.DataFrame([
        {"ジャンル": k, "応募数": v["application_count"], "返信率": v["response_rate"] or 0}
        for k, v in by_group.items()
    ])
    if group_df["応募数"].sum() > 0:
        chart = alt.Chart(group_df).mark_bar().encode(x="ジャンル:N", y="応募数:Q", tooltip=["ジャンル", "応募数", "返信率"])
        st.altair_chart(chart, width="stretch")
    else:
        st.info("データがありません。")

with g4:
    st.caption("曜日別応募・返信")
    by_weekday = analyze_by_weekday(records)
    weekday_df = pd.DataFrame([
        {"曜日": k, "応募数": v["application_count"], "返信率": v["response_rate"] or 0}
        for k, v in by_weekday.items()
    ])
    if weekday_df["応募数"].sum() > 0:
        chart = alt.Chart(weekday_df).mark_bar(color="#E45756").encode(x=alt.X("曜日:N", sort=None), y="応募数:Q")
        st.altair_chart(chart, width="stretch")
    else:
        st.info("データがありません。")

g5, g6 = st.columns(2)
with g5:
    st.caption("営業文タイプ別成果（返信率）")
    by_tone = analyze_by_tone(records)
    if by_tone:
        tone_df = pd.DataFrame([
            {"営業文タイプ": k, "返信率": v["response_rate"] or 0, "使用回数": v["usage_count"]}
            for k, v in by_tone.items()
        ])
        chart = alt.Chart(tone_df).mark_bar().encode(x="返信率:Q", y=alt.Y("営業文タイプ:N", sort="-x"), tooltip=["使用回数"])
        st.altair_chart(chart, width="stretch")
    else:
        st.info("データがありません。")

with g6:
    st.caption("スコア帯別成果（応募数）")
    by_score = analyze_by_total_score(records, jobs_for_scoring)
    score_df = pd.DataFrame([
        {"スコア帯": k, "応募数": v["application_count"], "案件数": v["job_count"]}
        for k, v in by_score.items()
    ])
    chart = alt.Chart(score_df).mark_bar(color="#F58518").encode(x=alt.X("スコア帯:N", sort=None), y="応募数:Q")
    st.altair_chart(chart, width="stretch")

with session() as conn:
    st.caption("ポートフォリオ別成果（返信率）")
    by_portfolio = analyze_by_portfolio(conn, records)
if by_portfolio:
    pf_df = pd.DataFrame([
        {"ポートフォリオ": k, "返信率": v["response_rate"] or 0, "使用回数": v["usage_count"]}
        for k, v in by_portfolio.items()
    ])
    chart = alt.Chart(pf_df).mark_bar(color="#72B7B2").encode(
        x="返信率:Q", y=alt.Y("ポートフォリオ:N", sort="-x"), tooltip=["使用回数"],
    )
    st.altair_chart(chart, width="stretch")
else:
    st.info("ポートフォリオを使用した応募データがありません。")

st.divider()

# ============================= 改善候補 =============================
st.subheader("💡 改善候補（統計に基づく気づき）")
st.caption("因果関係を断定するものではなく、あくまで傾向です。母数が少ない場合はその旨を明記しています。")
if insights:
    for text in insights:
        st.write(text)
else:
    st.info("気づきを表示するにはデータが不足しています。")

st.divider()

# ============================= データ品質 =============================
st.subheader("🔍 データ品質")
d1, d2, d3 = st.columns(3)
d1.metric("結果入力済み割合", f"{quality['result_input_rate']}%" if quality["result_input_rate"] is not None else "-")
d2.metric("結果不明件数", quality["unknown_status_count"])
d3.metric("対象応募件数", quality["total_records"])

d4, d5, d6 = st.columns(3)
d4.metric("契約金額未入力（採用済み）", quality["hired_missing_contract_amount_count"])
d5.metric("不採用理由未入力", quality["rejected_missing_reason_count"])
d6.metric("営業文タイプ欠損", quality["missing_tone_count"])

st.caption(f"ポートフォリオスナップショット欠損件数: {quality['missing_portfolio_snapshot_count']}件")
