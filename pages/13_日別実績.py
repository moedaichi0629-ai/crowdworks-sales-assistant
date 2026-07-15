"""過去の日別実績画面: 日付ごとの応募目標・実績・達成率・ジャンル別件数・上限超過の有無を確認する。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.daily.daily_dashboard_service import get_applied_category_breakdown
from src.daily.goal_service import get_goal_history
from src.database import init_db, session
from src.logger import get_logger
from src.repositories import get_application_records_for_date

st.set_page_config(page_title="日別実績 | クラウドワークス案件管理ツール", page_icon="📈", layout="wide")
logger = get_logger()
init_db()

st.title("📈 過去の日別実績")
st.caption("日付ごとの応募目標と実績（応募数・達成率・ジャンル別件数・上限超過の有無）を確認できます。")

with session() as conn:
    goals = get_goal_history(conn, limit=90)

if not goals:
    st.info("まだ日次目標のデータがありません。「本日の営業」ページを開くと自動的に作成されます。")
    st.stop()

rows = []
with session() as conn:
    for g in goals:
        target_date = g["target_date"]
        records = get_application_records_for_date(conn, target_date)
        applied_count = len(records)
        over_limit_count = sum(1 for r in records if r.get("is_over_limit"))
        target_count = int(g.get("target_count", 0) or 0)
        breakdown = get_applied_category_breakdown(conn, target_date)
        rows.append({
            "日付": target_date,
            "目標数": target_count,
            "上限数": g.get("maximum_count"),
            "応募数": applied_count,
            "達成率": round(applied_count / target_count * 100, 1) if target_count else 0.0,
            "AI・開発件数": breakdown["AI・開発"],
            "デザイン件数": breakdown["デザイン"],
            "その他件数": breakdown["その他"],
            "上限超過": "あり" if over_limit_count else "なし",
        })

df = pd.DataFrame(rows)
st.dataframe(
    df, width="stretch", hide_index=True,
    column_config={"達成率": st.column_config.NumberColumn("達成率(%)", format="%.1f%%")},
)

st.divider()
st.subheader("日別サマリー")
m1, m2, m3 = st.columns(3)
m1.metric("記録日数", len(df))
m2.metric("平均達成率", f"{df['達成率'].mean():.1f}%" if len(df) else "-")
m3.metric("上限超過があった日数", int((df["上限超過"] == "あり").sum()))
