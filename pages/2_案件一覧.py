"""案件一覧ページ: 検索・絞り込み・並べ替え・ステータス変更・メモ編集・書き出し。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.application.application_generator import GenerationBlockedError
from src.application.application_service import copy_application, generate_for_job
from src.config import JOB_STATUSES, JOB_TYPES, PORTFOLIO_TYPE_LABELS_JA
from src.database import init_db, session
from src.export import to_csv_bytes, to_excel_bytes
from src.filters import SORT_OPTIONS, apply_filters, apply_sort
from src.logger import get_logger
from src.portfolio.portfolio_service import get_selected_portfolios_with_detail
from src.repositories import (
    get_all_settings,
    get_job,
    get_jobs_with_latest_analysis,
    get_jobs_with_latest_application,
    list_application_drafts,
    update_favorite,
    update_memo,
    update_status_bulk,
)

st.set_page_config(page_title="案件一覧 | クラウドワークス案件管理ツール", page_icon="📄", layout="wide")
logger = get_logger()
init_db()

st.title("📄 案件一覧")

with session() as conn:
    jobs = get_jobs_with_latest_analysis(conn)
    settings = get_all_settings(conn)
    application_by_job = {j["id"]: j for j in get_jobs_with_latest_application(conn)}

_APPLICATION_FIELDS = [
    "draft_id", "preparation_status", "proposed_price", "proposed_delivery_days",
    "generation_type", "copied_at", "draft_updated_at", "selected_portfolio_ids_json",
]
for job in jobs:
    app_row = application_by_job.get(job["id"], {})
    for field in _APPLICATION_FIELDS:
        job[field] = app_row.get(field)

PRIORITY_BADGES = {
    "最優先": "🌟最優先", "優先": "🟢優先", "応募候補": "🔵応募候補",
    "要確認": "🟡要確認", "見送り候補": "⚪見送り候補",
}
RISK_BADGES = {"low": "🟢低", "medium": "🟡中", "high": "🟠高", "critical": "🔴非常に高い"}

if not jobs:
    st.info("まだ案件が登録されていません。「案件追加」ページから登録してください。")
    st.stop()

df = pd.DataFrame(jobs)

# ============================= 絞り込み =============================
with st.expander("🔍 絞り込み条件", expanded=True):
    c1, c2, c3, c4 = st.columns(4)
    free_word = c1.text_input("フリーワード")
    keyword_options = [""] + sorted([k for k in df["matched_keyword"].dropna().unique().tolist()])
    matched_keyword = c2.selectbox("検索キーワード", options=keyword_options)
    excluded_only_label = c3.selectbox("除外キーワード該当", options=["すべて", "該当あり", "該当なし"])
    status_filter = c4.multiselect("ステータス", options=JOB_STATUSES)

    c5, c6, c7, c8 = st.columns(4)
    min_budget = c5.number_input("最低予算", min_value=0, value=0, step=1000)
    max_budget = c6.number_input("最高予算", min_value=0, value=0, step=1000)
    job_type_filter = c7.selectbox("募集形式", options=[""] + JOB_TYPES)
    category_options = [""] + sorted([c for c in df["category"].dropna().unique().tolist()])
    category_filter = c8.selectbox("カテゴリ", options=category_options)

    c9, c10, c11, c12 = st.columns(4)
    deadline_to = c9.text_input("応募期限（この日付以前）", placeholder="2026-08-01")
    max_applicants = c10.number_input("応募人数（これ以下）", min_value=0, value=0, step=1)
    min_client_rating = c11.slider("クライアント評価（これ以上）", 0.0, 5.0, 0.0, 0.1)
    identity_filter = c12.selectbox("本人確認", options=["すべて", "確認済みのみ", "未確認のみ"])

    c13, c14 = st.columns(2)
    favorite_only = c13.checkbox("お気に入りのみ表示")
    source_type_filter = c14.selectbox("データ取得方法", options=["", "url", "manual", "csv"])

filters = {
    "free_word": free_word,
    "matched_keyword": matched_keyword,
    "excluded_only": True if excluded_only_label == "該当あり" else (False if excluded_only_label == "該当なし" else None),
    "min_budget": min_budget or None,
    "max_budget": max_budget or None,
    "job_type": job_type_filter,
    "category": category_filter,
    "deadline_to": deadline_to or None,
    "max_applicants": max_applicants if max_applicants > 0 else None,
    "min_client_rating": min_client_rating or None,
    "identity_verified": True if identity_filter == "確認済みのみ" else (False if identity_filter == "未確認のみ" else None),
    "status": status_filter or None,
    "is_favorite": favorite_only,
    "source_type": source_type_filter or None,
}

filtered_df = apply_filters(df, filters)

sort_label = st.selectbox("並べ替え", options=list(SORT_OPTIONS.keys()))
filtered_df = apply_sort(filtered_df, sort_label)

st.caption(f"{len(filtered_df)}件 / 全{len(df)}件")

# ============================= 一覧表示 =============================
display_df = filtered_df.copy()
display_df["応募優先度"] = display_df.get("application_priority", pd.Series(dtype=object)).apply(
    lambda p: PRIORITY_BADGES.get(p, "未分析") if p else "未分析"
)
display_df["危険レベル"] = display_df.get("risk_level", pd.Series(dtype=object)).apply(
    lambda r: RISK_BADGES.get(r, "-") if r else "-"
)
display_df["分析状況"] = display_df.get("analysis_id", pd.Series(dtype=object)).apply(
    lambda v: "分析済み" if pd.notna(v) else "未分析"
)
display_df["営業文作成状況"] = display_df.get("draft_id", pd.Series(dtype=object)).apply(
    lambda v: "作成済み" if pd.notna(v) else "未作成"
)
display_df["コピー済み"] = display_df.get("copied_at", pd.Series(dtype=object)).apply(
    lambda v: "済" if pd.notna(v) and v else "-"
)

display_columns = [
    "id", "is_favorite", "collected_at", "title", "job_type", "category", "budget_text",
    "published_at", "deadline", "applicant_count", "client_name", "client_rating",
    "identity_verified", "matched_keyword", "url", "status", "memo",
    "total_score", "ai_suitability_score", "safety_score", "応募優先度", "difficulty",
    "危険レベル", "分析状況", "analyzed_at",
    "営業文作成状況", "preparation_status", "proposed_price", "proposed_delivery_days", "コピー済み", "draft_updated_at",
]
display_columns = [c for c in display_columns if c in display_df.columns]

st.caption("スコア・優先度は「AI案件分析」ページで分析を実行すると表示されます（未分析の案件は「未分析」と表示されます）。")

st.dataframe(
    display_df[display_columns],
    width="stretch",
    hide_index=True,
    column_config={
        "id": st.column_config.NumberColumn("内部ID"),
        "is_favorite": st.column_config.CheckboxColumn("お気に入り"),
        "collected_at": "取得日時",
        "title": "案件タイトル",
        "job_type": "募集形式",
        "category": "カテゴリ",
        "budget_text": "予算",
        "published_at": "掲載日時",
        "deadline": "応募期限",
        "applicant_count": "応募人数",
        "client_name": "クライアント名",
        "client_rating": "クライアント評価",
        "identity_verified": st.column_config.CheckboxColumn("本人確認"),
        "matched_keyword": "検索キーワード",
        "url": st.column_config.LinkColumn("案件URL", display_text="開く"),
        "status": "ステータス",
        "memo": "メモ",
        "total_score": st.column_config.NumberColumn("総合スコア"),
        "ai_suitability_score": st.column_config.NumberColumn("AI適合度"),
        "safety_score": st.column_config.NumberColumn("安全度"),
        "difficulty": "難易度",
        "analyzed_at": "分析日時",
        "preparation_status": "応募準備ステータス",
        "proposed_price": st.column_config.NumberColumn("提案金額"),
        "proposed_delivery_days": st.column_config.NumberColumn("提案納期(日)"),
        "draft_updated_at": "営業文最終更新日時",
    },
)

# ============================= 書き出し =============================
col_dl1, col_dl2 = st.columns(2)
col_dl1.download_button(
    "CSVでダウンロード", data=to_csv_bytes(filtered_df), file_name="crowdworks_jobs.csv", mime="text/csv"
)
col_dl2.download_button(
    "Excelでダウンロード", data=to_excel_bytes(filtered_df), file_name="crowdworks_jobs.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

st.divider()

# ============================= 一括ステータス変更 =============================
st.subheader("✅ 一括ステータス変更")
id_to_title = dict(zip(filtered_df["id"], filtered_df["title"]))
selected_ids = st.multiselect(
    "対象案件を選択", options=list(id_to_title.keys()),
    format_func=lambda i: f"[{i}] {id_to_title.get(i, '')}",
)
bulk_status = st.selectbox("変更後のステータス", options=JOB_STATUSES, key="bulk_status")
if st.button("選択した案件のステータスを一括変更する"):
    if not selected_ids:
        st.warning("対象案件を1件以上選択してください。")
    else:
        try:
            with session() as conn:
                count = update_status_bulk(conn, selected_ids, bulk_status)
            st.success(f"{count}件のステータスを「{bulk_status}」に変更しました。")
            st.rerun()
        except Exception:
            logger.exception("一括ステータス変更に失敗しました。")
            st.error("ステータスの一括変更に失敗しました。")

st.divider()

# ============================= 詳細表示・個別編集 =============================
st.subheader("🔎 案件詳細・個別編集")
detail_id = st.selectbox(
    "案件を選択", options=list(id_to_title.keys()),
    format_func=lambda i: f"[{i}] {id_to_title.get(i, '')}", key="detail_select",
)

if detail_id is not None:
    with session() as conn:
        job = get_job(conn, int(detail_id))

    if job:
        st.markdown(f"### {job['title']}")
        if job.get("url"):
            st.markdown(f"[案件ページを開く]({job['url']})")

        info_cols = st.columns(4)
        info_cols[0].write(f"**募集形式**: {job.get('job_type') or '-'}")
        info_cols[1].write(f"**カテゴリ**: {job.get('category') or '-'}")
        info_cols[2].write(f"**予算**: {job.get('budget_text') or '-'}")
        info_cols[3].write(f"**応募期限**: {job.get('deadline') or '-'}")

        info_cols2 = st.columns(4)
        info_cols2[0].write(f"**応募人数**: {job.get('applicant_count') if job.get('applicant_count') is not None else '-'}")
        info_cols2[1].write(f"**採用人数**: {job.get('recruitment_count') if job.get('recruitment_count') is not None else '-'}")
        info_cols2[2].write(f"**クライアント名**: {job.get('client_name') or '-'}")
        info_cols2[3].write(f"**クライアント評価**: {job.get('client_rating') if job.get('client_rating') is not None else '-'}")

        with st.expander("案件本文を表示", expanded=False):
            st.text(job.get("body") or "（本文情報はありません）")

        edit_col1, edit_col2, edit_col3 = st.columns(3)
        new_status = edit_col1.selectbox(
            "ステータス", options=JOB_STATUSES,
            index=JOB_STATUSES.index(job["status"]) if job["status"] in JOB_STATUSES else 0,
            key=f"status_{detail_id}",
        )
        new_favorite = edit_col2.checkbox("お気に入り", value=bool(job.get("is_favorite")), key=f"fav_{detail_id}")
        new_memo = edit_col3.text_area("メモ", value=job.get("memo") or "", key=f"memo_{detail_id}")

        if st.button("この案件の内容を保存する", key=f"save_{detail_id}"):
            try:
                with session() as conn:
                    update_status_bulk(conn, [int(detail_id)], new_status)
                    update_favorite(conn, int(detail_id), new_favorite)
                    update_memo(conn, int(detail_id), new_memo)
                st.success("保存しました。")
                st.rerun()
            except Exception:
                logger.exception("案件詳細の保存に失敗しました。")
                st.error("保存に失敗しました。")

        st.markdown("---")
        st.markdown("#### 営業文・ポートフォリオ")
        with session() as conn:
            existing_drafts = list_application_drafts(conn, int(detail_id))
            selected_portfolios = get_selected_portfolios_with_detail(conn, int(detail_id))

        if selected_portfolios:
            names = "、".join(f"{p['title']}（{PORTFOLIO_TYPE_LABELS_JA.get(p.get('portfolio_type'), '-')}）" for p in selected_portfolios)
            st.caption(f"選択中のポートフォリオ（{len(selected_portfolios)}件）: {names}")
        else:
            st.caption("選択中のポートフォリオ: 未選択（営業文生成時に自動選択されます）")

        app_action_cols = st.columns(4)
        if app_action_cols[0].button("営業文を生成する", key=f"gen_app_{detail_id}"):
            try:
                with session() as conn:
                    generate_for_job(conn, int(detail_id))
                st.success("営業文を生成しました。「営業文一覧」ページで確認できます。")
                st.rerun()
            except GenerationBlockedError as e:
                st.error("危険案件の可能性があるため営業文生成を停止しました: " + " / ".join(e.reasons))
            except Exception:
                logger.exception("営業文生成に失敗しました。")
                st.error("営業文生成に失敗しました。")

        if app_action_cols[1].button("AI・開発ポートフォリオを優先選択", key=f"pf_dev_{detail_id}"):
            with session() as conn:
                from src.repositories import list_portfolios as _list_portfolios
                from src.repositories import get_profile as _get_profile
                prof = _get_profile(conn)
                dev_ids = [p["id"] for p in _list_portfolios(conn, prof["id"]) if p.get("for_development") and p.get("is_active", True)][:3]
                from src.portfolio.portfolio_service import update_manual_portfolio_selection
                update_manual_portfolio_selection(conn, int(detail_id), dev_ids)
            st.success("AI・開発ポートフォリオを選択しました。")
            st.rerun()

        if app_action_cols[2].button("デザインポートフォリオを優先選択", key=f"pf_design_{detail_id}"):
            with session() as conn:
                from src.repositories import list_portfolios as _list_portfolios
                from src.repositories import get_profile as _get_profile
                prof = _get_profile(conn)
                design_ids = [p["id"] for p in _list_portfolios(conn, prof["id"]) if p.get("for_design") and p.get("is_active", True)][:3]
                from src.portfolio.portfolio_service import update_manual_portfolio_selection
                update_manual_portfolio_selection(conn, int(detail_id), design_ids)
            st.success("デザインポートフォリオを選択しました。")
            st.rerun()

        if existing_drafts and app_action_cols[3].button("コピー済みにする", key=f"copy_{detail_id}"):
            with session() as conn:
                copy_application(conn, existing_drafts[0]["id"])
            st.success("コピー日時を記録しました。")
            st.rerun()

        nav_cols = st.columns(2)
        with nav_cols[0]:
            try:
                st.page_link("pages/9_営業文一覧.py", label="営業文一覧を開く", icon="📝")
            except Exception:
                st.caption("「営業文一覧」ページから詳細を確認できます。")
        with nav_cols[1]:
            try:
                st.page_link("pages/10_応募前確認.py", label="応募前確認画面を開く", icon="✅")
            except Exception:
                st.caption("「応募前確認」ページから最終確認ができます。")
