"""分析結果一覧ページ: AI分析結果の一覧表示・絞り込み・並べ替え・詳細確認。"""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from src.analysis.analysis_service import analyze_single_job
from src.config import (
    BUDGET_EVALUATION_LABELS_JA,
    DIFFICULTY_LABELS_JA,
    JOB_STATUSES,
    RECOMMENDATION_LABELS_JA,
    RISK_LEVEL_LABELS_JA,
    STATUS_CANDIDATE,
    STATUS_SKIPPED,
)
from src.database import init_db, session
from src.filters import ANALYSIS_SORT_OPTIONS, apply_analysis_filters, apply_sort
from src.logger import get_logger
from src.repositories import get_jobs_with_latest_analysis, update_status_bulk

st.set_page_config(page_title="分析結果一覧 | クラウドワークス案件管理ツール", page_icon="📊", layout="wide")
logger = get_logger()
init_db()

st.title("📊 分析結果一覧")

with session() as conn:
    jobs = get_jobs_with_latest_analysis(conn)

if not jobs:
    st.info("まだ案件が登録されていません。")
    st.stop()

df = pd.DataFrame(jobs)

PRIORITY_BADGES = {
    "最優先": "🌟最優先", "優先": "🟢優先", "応募候補": "🔵応募候補",
    "要確認": "🟡要確認", "見送り候補": "⚪見送り候補",
}
RISK_BADGES = {"low": "🟢低", "medium": "🟡中", "high": "🟠高", "critical": "🔴非常に高い"}


def _priority_badge(p):
    return PRIORITY_BADGES.get(p, "未分析") if p else "未分析"


def _risk_badge(r):
    return RISK_BADGES.get(r, "-") if r else "-"


# ============================= 絞り込み =============================
with st.expander("🔍 絞り込み条件", expanded=True):
    c1, c2, c3, c4 = st.columns(4)
    min_total_score = c1.number_input("総合スコア（これ以上）", min_value=0, max_value=100, value=0)
    min_ai_score = c2.number_input("AI適合度（これ以上）", min_value=0, max_value=100, value=0)
    min_safety_score = c3.number_input("安全度（これ以上）", min_value=0, max_value=100, value=0)
    analyzed_state = c4.selectbox("分析状況", options=["すべて", "分析済みのみ", "未分析のみ"])

    c5, c6, c7, c8 = st.columns(4)
    priority_filter = c5.multiselect("応募優先度", options=["最優先", "優先", "応募候補", "要確認", "見送り候補"])
    recommendation_filter = c6.multiselect(
        "応募推奨度", options=list(RECOMMENDATION_LABELS_JA.keys()),
        format_func=lambda v: RECOMMENDATION_LABELS_JA.get(v, v),
    )
    difficulty_filter = c7.multiselect(
        "難易度", options=list(DIFFICULTY_LABELS_JA.keys()), format_func=lambda v: DIFFICULTY_LABELS_JA.get(v, v),
    )
    risk_filter = c8.multiselect(
        "危険レベル", options=list(RISK_LEVEL_LABELS_JA.keys()), format_func=lambda v: RISK_LEVEL_LABELS_JA.get(v, v),
    )

    c9, c10, c11 = st.columns(3)
    budget_eval_filter = c9.multiselect(
        "予算評価", options=list(BUDGET_EVALUATION_LABELS_JA.keys()), format_func=lambda v: BUDGET_EVALUATION_LABELS_JA.get(v, v),
    )
    status_filter = c10.multiselect("ステータス", options=JOB_STATUSES)
    skill_keyword = c11.text_input("必要スキル・一致スキルで検索")

filters = {
    "min_total_score": min_total_score or None,
    "min_ai_score": min_ai_score or None,
    "min_safety_score": min_safety_score or None,
    "application_priority": priority_filter or None,
    "recommendation": recommendation_filter or None,
    "difficulty": difficulty_filter or None,
    "risk_level": risk_filter or None,
    "budget_evaluation": budget_eval_filter or None,
    "analyzed_state": analyzed_state if analyzed_state != "すべて" else None,
    "skill_keyword": skill_keyword or None,
    "skill_field": "required_skills",
}

filtered_df = apply_analysis_filters(df, filters)
if status_filter:
    filtered_df = filtered_df[filtered_df["status"].isin(status_filter)]

sort_label = st.selectbox("並べ替え", options=list(ANALYSIS_SORT_OPTIONS.keys()))
filtered_df = apply_sort(filtered_df, sort_label, options=ANALYSIS_SORT_OPTIONS)

st.caption(f"{len(filtered_df)}件 / 全{len(df)}件")

# ============================= 一覧表示 =============================
display_df = filtered_df.copy()
display_df["応募優先度"] = display_df["application_priority"].apply(_priority_badge)
display_df["危険レベル"] = display_df["risk_level"].apply(_risk_badge)
display_df["予想作業時間"] = display_df.apply(
    lambda r: f"{r['estimated_hours_min']}〜{r['estimated_hours_max']}h" if pd.notna(r.get("estimated_hours_min")) else "-",
    axis=1,
)
display_df["分析状況"] = display_df["analysis_id"].apply(lambda v: "分析済み" if pd.notna(v) else "未分析")
display_df["一致スキル数"] = display_df["matched_skills"].apply(lambda v: len(v) if isinstance(v, list) else 0)
display_df["不足スキル数"] = display_df["missing_skills"].apply(lambda v: len(v) if isinstance(v, list) else 0)
display_df["関連ポートフォリオ"] = display_df["matched_portfolio"].apply(
    lambda v: "、".join(v) if isinstance(v, list) and v else "-"
)

show_cols = [
    "title", "total_score", "ai_suitability_score", "rule_based_score", "safety_score",
    "応募優先度", "recommendation", "difficulty", "budget_evaluation", "予想作業時間",
    "危険レベル", "一致スキル数", "不足スキル数", "関連ポートフォリオ", "analyzed_at", "url", "分析状況",
]
show_cols = [c for c in show_cols if c in display_df.columns]

st.dataframe(
    display_df[show_cols],
    width="stretch",
    hide_index=True,
    column_config={
        "title": "案件タイトル",
        "total_score": st.column_config.NumberColumn("総合スコア"),
        "ai_suitability_score": st.column_config.NumberColumn("AI適合度"),
        "rule_based_score": st.column_config.NumberColumn("ルールベース"),
        "safety_score": st.column_config.NumberColumn("安全度"),
        "recommendation": "応募推奨度",
        "difficulty": "難易度",
        "budget_evaluation": "予算評価",
        "analyzed_at": "分析日時",
        "url": st.column_config.LinkColumn("案件URL", display_text="開く"),
    },
)

st.divider()

# ============================= 詳細表示 =============================
st.subheader("🔎 分析詳細")
id_to_title = dict(zip(filtered_df["id"], filtered_df["title"]))
if not id_to_title:
    st.info("表示できる案件がありません。")
    st.stop()

detail_id = st.selectbox(
    "案件を選択", options=list(id_to_title.keys()), format_func=lambda i: f"[{i}] {id_to_title.get(i, '')}",
)

with session() as conn:
    detail_jobs = {j["id"]: j for j in get_jobs_with_latest_analysis(conn)}
job = detail_jobs.get(detail_id)

if job:
    st.markdown(f"### {job['title']}")
    info_cols = st.columns(4)
    info_cols[0].write(f"**募集形式**: {job.get('job_type') or '-'}")
    info_cols[1].write(f"**予算**: {job.get('budget_text') or '-'}")
    info_cols[2].write(f"**応募期限**: {job.get('deadline') or '-'}")
    info_cols[3].write(f"**ステータス**: {job.get('status')}")

    with st.expander("案件本文を表示"):
        st.text(job.get("body") or "（本文情報はありません）")

    if job.get("analysis_id") is None:
        st.warning("この案件はまだ分析されていません。「AI案件分析」ページから分析を実行してください。")
    else:
        risk_level = job.get("risk_level")
        if risk_level in ("high", "critical"):
            st.error(f"⚠️ 危険レベル: {RISK_LEVEL_LABELS_JA.get(risk_level, risk_level)}。応募前に内容を十分ご確認ください。")

        score_cols = st.columns(5)
        score_cols[0].metric("総合スコア", job.get("total_score"))
        score_cols[1].metric("AI適合度", job.get("ai_suitability_score") if job.get("ai_suitability_score") is not None else "未使用")
        score_cols[2].metric("ルールベース", job.get("rule_based_score"))
        score_cols[3].metric("安全度", job.get("safety_score"))
        score_cols[4].metric("応募優先度", _priority_badge(job.get("application_priority")))

        st.write(f"**案件要約**: {job.get('summary') or '-'}")
        st.write(f"**難易度**: {DIFFICULTY_LABELS_JA.get(job.get('difficulty'), job.get('difficulty'))}")
        st.write(f"**予算評価**: {BUDGET_EVALUATION_LABELS_JA.get(job.get('budget_evaluation'), job.get('budget_evaluation'))}")
        hmin, hmax, days = job.get("estimated_hours_min"), job.get("estimated_hours_max"), job.get("estimated_days")
        st.write(f"**予想作業時間**: {hmin}〜{hmax}時間（約{days}日）" if hmin is not None else "**予想作業時間**: 不明")

        detail_cols = st.columns(2)
        with detail_cols[0]:
            st.markdown("**クライアントの要望**")
            st.write("、".join(job.get("client_needs") or []) or "-")
            st.markdown("**必要スキル**")
            st.write("、".join(job.get("required_skills") or []) or "-")
            st.markdown("**一致スキル**")
            st.write("、".join(job.get("matched_skills") or []) or "-")
            st.markdown("**不足スキル**")
            st.write("、".join(job.get("missing_skills") or []) or "-")
            st.markdown("**関連ポートフォリオ**")
            st.write("、".join(job.get("matched_portfolio") or []) or "-")
        with detail_cols[1]:
            st.markdown("**応募時の強み**")
            st.write("、".join(job.get("strengths") or []) or "-")
            st.markdown("**注意点**")
            st.write("、".join(job.get("concerns") or []) or "-")
            st.markdown("**応募前に確認する質問**")
            st.write("、".join(job.get("questions") or []) or "-")
            st.markdown("**応募方針**")
            st.write(job.get("application_strategy") or "-")

        st.markdown("**AIの判定理由**")
        st.write(job.get("analysis_reason") or "-")

        st.markdown("---")
        st.markdown("**安全性分析**")
        safety_cols = st.columns(2)
        safety_cols[0].write(f"推奨行動: {job.get('recommended_action') or '-'}")
        safety_cols[1].write(f"安全性の要約: {job.get('safety_summary') or '-'}")
        risks = job.get("detected_risks") or []
        if risks:
            for r in risks:
                if isinstance(r, dict):
                    src = "AI判定" if r.get("source") == "ai" else "キーワード一致"
                    st.write(f"- {r.get('category')}（{src}）")
        else:
            st.write("検出されたリスクはありません。")

        st.caption(
            f"分析: {job.get('provider') or 'rule_only'} / {job.get('model') or '-'} / "
            f"{job.get('analyzed_at') or '-'}"
        )
        if job.get("analysis_error"):
            st.warning(f"分析時のエラー: {job['analysis_error']}")

    st.markdown("---")
    btn_cols = st.columns(6)
    if btn_cols[0].button("再分析", key=f"reanalyze_{detail_id}"):
        try:
            with session() as conn:
                analyze_single_job(conn, int(detail_id), force_reanalyze=True)
            st.success("再分析しました。")
            st.rerun()
        except Exception:
            logger.exception("再分析に失敗しました。")
            st.error("再分析に失敗しました。")

    if btn_cols[1].button("ルールベースのみ再計算", key=f"rule_only_{detail_id}"):
        try:
            with session() as conn:
                analyze_single_job(conn, int(detail_id), force_reanalyze=True, rule_only=True)
            st.success("ルールベースのみで再計算しました。")
            st.rerun()
        except Exception:
            logger.exception("ルールベース再計算に失敗しました。")
            st.error("再計算に失敗しました。")

    if btn_cols[2].button("応募候補に変更", key=f"to_candidate_{detail_id}"):
        with session() as conn:
            update_status_bulk(conn, [int(detail_id)], STATUS_CANDIDATE)
        st.success("応募候補に変更しました。")
        st.rerun()

    if btn_cols[3].button("見送りに変更", key=f"to_skip_{detail_id}"):
        with session() as conn:
            update_status_bulk(conn, [int(detail_id)], STATUS_SKIPPED)
        st.success("見送りに変更しました。")
        st.rerun()

    if job.get("url"):
        btn_cols[5].markdown(f"[案件ページを開く]({job['url']})")

    if job.get("analysis_id") is not None:
        copy_payload = {
            "title": job.get("title"), "total_score": job.get("total_score"),
            "application_priority": job.get("application_priority"),
            "recommendation": job.get("recommendation"), "summary": job.get("summary"),
            "matched_skills": job.get("matched_skills"), "missing_skills": job.get("missing_skills"),
            "strengths": job.get("strengths"), "concerns": job.get("concerns"),
            "application_strategy": job.get("application_strategy"),
        }
        with st.expander("判定結果をコピー（右上のコピーアイコンを使用）"):
            st.code(json.dumps(copy_payload, ensure_ascii=False, indent=2), language="json")
