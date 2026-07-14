"""クラウドワークス案件収集・管理ツール - ダッシュボード（トップページ）。"""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from src.database import init_db, session
from src.logger import get_logger
from src.repositories import (
    get_counts_by_column,
    get_dashboard_counts,
    get_recent_7days_counts,
)

st.set_page_config(page_title="クラウドワークス案件管理ツール", page_icon="📋", layout="wide")

logger = get_logger()


@st.cache_resource
def _ensure_db_initialized() -> bool:
    init_db()
    logger.info("アプリを起動しました。")
    return True


def render_dashboard() -> None:
    st.title("📋 クラウドワークス案件収集・管理ツール")
    st.caption("案件の収集・登録・一覧管理を行うダッシュボードです（第1段階：自動応募機能は含みません）。")

    try:
        with session() as conn:
            counts = get_dashboard_counts(conn)
            recent = get_recent_7days_counts(conn)
            by_job_type = get_counts_by_column(conn, "job_type")
            by_keyword = get_counts_by_column(conn, "matched_keyword")
            by_status = get_counts_by_column(conn, "status")
    except Exception:
        logger.exception("ダッシュボードの集計取得に失敗しました。")
        st.error(
            "ダッシュボードの情報取得に失敗しました。データベースファイルが壊れていないか確認してください。"
            "詳細はlogs/app.logをご確認ください。"
        )
        return

    st.subheader("サマリー")
    row1 = st.columns(4)
    row1[0].metric("保存案件数", counts["total_jobs"])
    row1[1].metric("本日取得した案件数", counts["today_collected"])
    row1[2].metric("未確認案件数", counts["unconfirmed"])
    row1[3].metric("確認済み案件数", counts["confirmed"])

    row2 = st.columns(3)
    row2[0].metric("応募候補数", counts["candidate"])
    row2[1].metric("見送り数", counts["skipped"])
    row2[2].metric("応募済み数", counts["applied"])

    st.divider()
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("直近7日間の案件取得数")
        if recent:
            df = pd.DataFrame(recent)
            chart = (
                alt.Chart(df)
                .mark_bar(color="#4C78A8")
                .encode(x=alt.X("day:O", title="日付"), y=alt.Y("count:Q", title="取得数"))
            )
            st.altair_chart(chart, width="stretch")
        else:
            st.info("まだ案件が登録されていません。")

    with col_b:
        st.subheader("募集形式ごとの案件数")
        if by_job_type:
            df = pd.DataFrame(by_job_type)
            chart = (
                alt.Chart(df)
                .mark_arc()
                .encode(theta="count:Q", color="label:N", tooltip=["label", "count"])
            )
            st.altair_chart(chart, width="stretch")
        else:
            st.info("まだ案件が登録されていません。")

    col_c, col_d = st.columns(2)
    with col_c:
        st.subheader("検索キーワードごとの案件数")
        if by_keyword:
            st.dataframe(pd.DataFrame(by_keyword).rename(columns={"label": "キーワード", "count": "件数"}), width="stretch", hide_index=True)
        else:
            st.info("まだ案件が登録されていません。")

    with col_d:
        st.subheader("ステータスごとの案件数")
        if by_status:
            st.dataframe(pd.DataFrame(by_status).rename(columns={"label": "ステータス", "count": "件数"}), width="stretch", hide_index=True)
        else:
            st.info("まだ案件が登録されていません。")

    st.divider()
    st.info(
        "左側のメニューから「案件追加」で新しい案件を登録、「案件一覧」で保存済み案件の確認・管理、"
        "「設定」で検索条件の調整ができます。"
    )


_ensure_db_initialized()
render_dashboard()
