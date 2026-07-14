"""AI案件分析ページ: 単体分析・一括分析の実行画面。"""
from __future__ import annotations

import streamlit as st

from src.ai.provider_factory import is_provider_available
from src.analysis.analysis_service import run_bulk_analysis, select_target_jobs
from src.config import AI_PROVIDER_NONE
from src.database import init_db, session
from src.logger import get_logger
from src.repositories import get_all_analysis_settings, get_analysis_dashboard_counts

st.set_page_config(page_title="AI案件分析 | クラウドワークス案件管理ツール", page_icon="🤖", layout="wide")
logger = get_logger()
init_db()

st.title("🤖 AI案件分析")
st.caption("ルールベース一次判定・危険案件検出・AIによる適合度分析をまとめて実行します。")

with session() as conn:
    counts = get_analysis_dashboard_counts(conn)
    analysis_settings = get_all_analysis_settings(conn)

col1, col2 = st.columns(2)
col1.metric("未分析案件数", counts["unanalyzed"])
col2.metric("分析済み案件数", counts["analyzed"])

provider = analysis_settings.get("ai_provider", AI_PROVIDER_NONE)
model = (analysis_settings.get("ai_models") or {}).get(provider)
provider_ready = is_provider_available(provider)

if provider == AI_PROVIDER_NONE:
    st.info("現在の設定: AIプロバイダー『使用しない』。ルールベース分析のみで実行されます。「AI分析設定」ページから変更できます。")
elif not provider_ready:
    st.warning(
        f"AIプロバイダー『{provider}』が選択されていますが、APIキーが未設定のため、"
        "AI分析は利用できません。.envにAPIキーを設定するか、ルールベースのみで実行してください。"
    )
else:
    st.success(f"AIプロバイダー: {provider} / モデル: {model or '(既定値)'}")

st.divider()
st.subheader("分析対象の選択")

target_mode = st.selectbox(
    "分析対象",
    options=["未分析案件のみ", "選択した案件", "応募候補ステータスのみ", "本日取得した案件", "条件に合う案件", "全案件を再分析"],
)

with session() as conn:
    if target_mode == "選択した案件":
        from src.repositories import get_jobs_with_latest_analysis
        all_jobs = get_jobs_with_latest_analysis(conn)
        id_to_title = {j["id"]: j["title"] for j in all_jobs}
        selected_ids = st.multiselect(
            "対象案件", options=list(id_to_title.keys()), format_func=lambda i: f"[{i}] {id_to_title.get(i, '')}",
        )
    else:
        selected_ids = None

    condition_min_budget = condition_max_applicants = condition_min_rating = None
    if target_mode == "条件に合う案件":
        cc1, cc2, cc3 = st.columns(3)
        condition_min_budget = cc1.number_input("最低予算", min_value=0, value=int(analysis_settings.get("min_budget_for_analysis", 0)), step=1000)
        condition_max_applicants = cc2.number_input("最大応募人数（0で無制限）", min_value=0, value=int(analysis_settings.get("max_applicant_count", 0)))
        condition_min_rating = cc3.number_input("最低クライアント評価", min_value=0.0, max_value=5.0, value=float(analysis_settings.get("min_client_rating", 0.0)), step=0.1)

    target_jobs = select_target_jobs(conn, target_mode, selected_ids)

    if target_mode == "条件に合う案件":
        def _match(j: dict) -> bool:
            if condition_min_budget and (j.get("budget_max") or 0) < condition_min_budget:
                return False
            if condition_max_applicants and (j.get("applicant_count") or 0) > condition_max_applicants:
                return False
            if condition_min_rating and (j.get("client_rating") or 0) < condition_min_rating:
                return False
            return True
        target_jobs = [j for j in target_jobs if _match(j)]

st.write(f"対象案件数: **{len(target_jobs)}件**")

st.divider()
st.subheader("実行設定")

col_a, col_b, col_c = st.columns(3)
max_count = col_a.number_input(
    "一括分析件数（上限）", min_value=1, max_value=200,
    value=int(analysis_settings.get("bulk_analysis_max_count", 10)),
)
wait_seconds = col_b.number_input(
    "分析間の待機秒数", min_value=0.0, max_value=30.0,
    value=float(analysis_settings.get("analysis_wait_seconds", 2.0)), step=0.5,
)
min_body_chars = col_c.number_input(
    "最低限必要な案件本文文字数", min_value=0, max_value=1000,
    value=int(analysis_settings.get("min_body_chars_for_analysis", 20)),
)

col_d, col_e = st.columns(2)
rule_only = col_d.checkbox("ルールベースのみで実行する（AIを使わない）", value=(provider == AI_PROVIDER_NONE or not provider_ready))
force_reanalyze = col_e.checkbox("強制再分析する（キャッシュを無視する）", value=False)

if st.button("分析を開始する", type="primary", disabled=(len(target_jobs) == 0)):
    if analysis_settings.get("min_body_chars_for_analysis") != min_body_chars:
        with session() as conn:
            from src.repositories import save_analysis_setting
            save_analysis_setting(conn, "min_body_chars_for_analysis", int(min_body_chars))

    job_ids = [j["id"] for j in target_jobs]
    progress_bar = st.progress(0.0, text="分析を開始します…")

    def _on_progress(done: int, total: int) -> None:
        progress_bar.progress(done / total if total else 1.0, text=f"分析中… {done}/{total}件")

    try:
        with session() as conn:
            summary = run_bulk_analysis(
                conn, job_ids, wait_seconds=float(wait_seconds), max_count=int(max_count),
                force_reanalyze=force_reanalyze, rule_only=rule_only, progress_callback=_on_progress,
            )
        progress_bar.progress(1.0, text="完了しました。")

        if summary.get("error"):
            st.error(summary["error"])
        else:
            st.success("分析が完了しました。")
            m1, m2, m3, m4, m5, m6 = st.columns(6)
            m1.metric("成功件数", summary["success"])
            m2.metric("失敗件数", summary["failed"])
            m3.metric("スキップ件数", summary["skipped"])
            m4.metric("API使用件数", summary["api_used"])
            m5.metric("ルールベースのみ", summary["rule_only"])
            m6.metric("キャッシュ利用", summary["cache_used"])
            st.info("結果は「分析結果一覧」ページで確認できます。")
    except Exception:
        logger.exception("一括分析の実行に失敗しました。")
        st.error("分析処理中に予期しないエラーが発生しました。詳細はlogs/app.logをご確認ください。")
