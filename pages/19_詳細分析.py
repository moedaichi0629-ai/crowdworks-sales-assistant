"""詳細分析: ジャンル・営業文・ポートフォリオ・金額・納期・曜日/時間帯・スコア・クライアント・
不採用理由ごとの詳細な成果分析と、各種データのCSV/Excel出力。
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.analytics.analytics_export import (
    build_anonymized_dataset_df,
    build_application_history_df,
    build_category_summary_df,
    build_goal_history_df,
    build_interview_history_df,
    build_kpi_summary_df,
    build_portfolio_summary_df,
    build_response_history_df,
    build_result_history_df,
    build_tone_summary_df,
    to_csv_bytes,
    to_excel_bytes_multi,
)
from src.analytics.category_analytics import analyze_by_category_group, analyze_by_subcategory
from src.analytics.kpi_service import compute_kpis, get_base_records
from src.analytics.message_analytics import analyze_by_tone
from src.analytics.period_service import PERIOD_ALL, PERIOD_CUSTOM, PERIOD_OPTIONS, resolve_period
from src.analytics.portfolio_analytics import analyze_by_portfolio
from src.analytics.price_analytics import analyze_by_delivery_band, analyze_by_price_band
from src.analytics.result_analytics import analyze_by_client_info, analyze_improvement_points, analyze_rejection_reasons
from src.analytics.score_analytics import (
    analyze_by_ai_score,
    analyze_by_daily_priority_score,
    analyze_by_portfolio_relevance,
    analyze_by_safety_score,
    analyze_by_total_score,
)
from src.analytics.timing_analytics import analyze_by_freshness, analyze_by_hour, analyze_by_weekday
from src.database import init_db, session
from src.logger import get_logger
from src.repositories import get_portfolio_average_relevance, list_jobs_with_analysis_for_scoring

st.set_page_config(page_title="詳細分析 | クラウドワークス案件管理ツール", page_icon="🔬", layout="wide")
logger = get_logger()
init_db()

st.title("🔬 詳細分析")

col_period, col_from, col_to = st.columns([2, 1, 1])
period = col_period.selectbox("期間", options=PERIOD_OPTIONS, index=PERIOD_OPTIONS.index(PERIOD_ALL))
custom_from = custom_to = None
if period == PERIOD_CUSTOM:
    custom_from = col_from.date_input("開始日").isoformat()
    custom_to = col_to.date_input("終了日").isoformat()
date_from, date_to = resolve_period(period, custom_from, custom_to)
st.caption(f"集計期間: {date_from} 〜 {date_to}（日本時間）")

with session() as conn:
    records = get_base_records(conn, date_from, date_to)

if not records:
    st.info("この期間の応募データがまだありません。")

category = st.selectbox(
    "分析カテゴリ",
    options=["ジャンル", "営業文", "ポートフォリオ", "金額", "納期", "曜日・時間帯", "スコア", "クライアント", "不採用理由", "出力"],
)


def _dict_to_table(d: dict) -> pd.DataFrame:
    return pd.DataFrame([{"項目": k, **v} for k, v in d.items()])


if category == "ジャンル":
    st.subheader("ジャンル別成果（大分類）")
    st.dataframe(_dict_to_table(analyze_by_category_group(records)), width="stretch", hide_index=True)
    st.subheader("細分類別成果")
    sub = analyze_by_subcategory(records)
    if sub:
        st.dataframe(_dict_to_table(sub), width="stretch", hide_index=True)
    else:
        st.info("細分類に該当するデータがありません。")

elif category == "営業文":
    st.subheader("営業文タイプ別成果")
    st.caption("使用回数が5件未満の分類は「参考値」です。")
    by_tone = analyze_by_tone(records)
    if by_tone:
        df = _dict_to_table(by_tone)
        st.dataframe(df, width="stretch", hide_index=True)
    else:
        st.info("データがありません。")

elif category == "ポートフォリオ":
    st.subheader("ポートフォリオ別成果")
    st.caption("1件の応募で複数のポートフォリオを使用した場合は、それぞれの使用回数に含まれます。単独の効果ではありません。")
    with session() as conn:
        by_portfolio = analyze_by_portfolio(conn, records)
    if by_portfolio:
        df = _dict_to_table(by_portfolio)
        st.dataframe(df, width="stretch", hide_index=True)
    else:
        st.info("ポートフォリオを使用した応募データがありません。")

elif category == "金額":
    st.subheader("応募金額帯別成果")
    by_price = analyze_by_price_band(records)
    for contract_type, bands in by_price.items():
        st.markdown(f"#### {contract_type}")
        if bands:
            st.dataframe(_dict_to_table(bands), width="stretch", hide_index=True)
        else:
            st.info("データがありません。")

elif category == "納期":
    st.subheader("提案納期帯別成果")
    by_delivery = analyze_by_delivery_band(records)
    if by_delivery:
        rows = []
        for label, stats in by_delivery.items():
            row = {"納期帯": label, **{k: v for k, v in stats.items() if k != "by_category_group"}}
            for group, count in (stats.get("by_category_group") or {}).items():
                row[f"内訳:{group}"] = count
            rows.append(row)
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    else:
        st.info("データがありません。")

elif category == "曜日・時間帯":
    st.subheader("曜日別成果")
    st.dataframe(_dict_to_table(analyze_by_weekday(records)), width="stretch", hide_index=True)
    st.subheader("時間帯別成果")
    st.dataframe(_dict_to_table(analyze_by_hour(records)), width="stretch", hide_index=True)
    st.subheader("掲載からの経過時間別成果")
    st.caption("因果関係を示すものではなく、傾向の把握を目的としています。")
    st.dataframe(_dict_to_table(analyze_by_freshness(records)), width="stretch", hide_index=True)

elif category == "スコア":
    with session() as conn:
        jobs = list_jobs_with_analysis_for_scoring(conn)
        avg_relevance = get_portfolio_average_relevance(conn)
    st.subheader("総合スコア帯別成果")
    st.dataframe(_dict_to_table(analyze_by_total_score(records, jobs)), width="stretch", hide_index=True)
    st.subheader("AI適合度帯別成果")
    st.dataframe(_dict_to_table(analyze_by_ai_score(records, jobs)), width="stretch", hide_index=True)
    st.subheader("安全度帯別成果")
    st.dataframe(_dict_to_table(analyze_by_safety_score(records, jobs)), width="stretch", hide_index=True)
    st.subheader("デイリー優先スコア帯別成果")
    st.dataframe(_dict_to_table(analyze_by_daily_priority_score(records)), width="stretch", hide_index=True)
    st.subheader("ポートフォリオ関連度帯別成果（参考値）")
    st.dataframe(_dict_to_table(analyze_by_portfolio_relevance(records, avg_relevance)), width="stretch", hide_index=True)

elif category == "クライアント":
    info = analyze_by_client_info(records)
    st.subheader("本人確認の有無")
    st.dataframe(
        _dict_to_table({"本人確認済み": info["identity_verified"], "未確認": info["identity_unverified"]}),
        width="stretch", hide_index=True,
    )
    st.subheader("クライアント評価帯")
    st.dataframe(_dict_to_table(info["by_rating"]), width="stretch", hide_index=True)
    st.subheader("応募人数帯")
    st.dataframe(_dict_to_table(info["by_applicant_count"]), width="stretch", hide_index=True)
    st.caption(f"平均採用予定人数: {info['avg_recruitment_count'] if info['avg_recruitment_count'] is not None else '-'}")

elif category == "不採用理由":
    st.subheader("不採用理由")
    rejection = analyze_rejection_reasons(records)
    st.write(f"不採用件数: {rejection['total_rejected']}件")
    if rejection["by_reason"]:
        df = pd.DataFrame([{"理由": k, "件数": v} for k, v in rejection["by_reason"].items()])
        st.dataframe(df, width="stretch", hide_index=True)
    else:
        st.info("不採用データがありません。")

    st.subheader("改善点の頻出キーワード")
    st.caption("自由記述から単純なキーワード頻度を集計したものです（外部AIへは送信していません）。")
    keywords = analyze_improvement_points(records)
    if keywords:
        st.dataframe(pd.DataFrame(keywords, columns=["キーワード", "出現回数"]), width="stretch", hide_index=True)
    else:
        st.info("改善点の記録がありません。")

elif category == "出力":
    st.subheader("CSV・Excel出力")
    st.caption("個人情報を含む出力と、匿名化された分析用出力を分けています。")

    with session() as conn:
        kpis = compute_kpis(conn, date_from, date_to)
        app_df = build_application_history_df(records)
        response_df = build_response_history_df(conn)
        interview_df = build_interview_history_df(conn)
        result_df = build_result_history_df(conn)
        goal_df = build_goal_history_df(conn)
        category_df = build_category_summary_df(records)
        tone_df = build_tone_summary_df(records)
        portfolio_df = build_portfolio_summary_df(conn, records)
        kpi_df = build_kpi_summary_df(kpis)
        anonymized_df = build_anonymized_dataset_df(records)

    st.markdown("#### 個人情報を含む出力")
    datasets = {
        "応募履歴": app_df, "返信履歴": response_df, "面談履歴": interview_df,
        "採用・不採用結果": result_df, "日別目標実績": goal_df, "ジャンル別集計": category_df,
        "営業文タイプ別集計": tone_df, "ポートフォリオ別集計": portfolio_df, "KPIサマリー": kpi_df,
    }
    for name, df in datasets.items():
        c1, c2, c3 = st.columns([2, 1, 1])
        c1.write(f"{name}（{len(df)}件）")
        c2.download_button(
            "CSVダウンロード", data=to_csv_bytes(df), file_name=f"{name}.csv", mime="text/csv", key=f"csv_{name}",
        )
        c3.download_button(
            "Excelダウンロード", data=to_excel_bytes_multi({name: df}), file_name=f"{name}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"xlsx_{name}",
        )

    st.markdown("#### まとめてExcel出力（複数シート）")
    st.download_button(
        "全データをExcelでダウンロード", data=to_excel_bytes_multi(datasets), file_name="営業成績データ.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.divider()
    st.markdown("#### 分析用匿名化データ（将来のAI改善用データ基盤）")
    st.caption(
        "クライアント名・本文中の個人情報・メールアドレス・電話番号・面談URL・詳細な返信本文・秘密情報は含みません。"
        "現時点ではAI学習へは自動反映されません（第8段階での活用を想定したデータ整備のみ）。"
    )
    st.dataframe(anonymized_df.head(20), width="stretch", hide_index=True)
    c1, c2 = st.columns(2)
    c1.download_button(
        "匿名化データCSV", data=to_csv_bytes(anonymized_df), file_name="匿名化分析用データ.csv", mime="text/csv",
    )
    c2.download_button(
        "匿名化データExcel", data=to_excel_bytes_multi({"匿名化データ": anonymized_df}),
        file_name="匿名化分析用データ.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
