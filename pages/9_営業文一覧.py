"""営業文一覧ページ: 生成済み営業文の一覧・詳細確認・編集・コピー・履歴管理。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.application.application_generator import GenerationBlockedError
from src.application.application_service import (
    EDIT_INSTRUCTION_MAP,
    copy_application,
    edit_with_instruction,
    generate_for_job,
    manual_edit_application,
)
from src.application.version_service import get_version_history, revert_to_version
from src.config import PREP_STATUS_APPLIED, PREPARATION_STATUSES, STATUS_SKIPPED
from src.database import init_db, session
from src.logger import get_logger
from src.repositories import (
    get_jobs_with_latest_application,
    list_application_drafts,
    update_application_draft,
    update_status_bulk,
)

st.set_page_config(page_title="営業文一覧 | クラウドワークス案件管理ツール", page_icon="📝", layout="wide")
logger = get_logger()
init_db()

st.title("📝 営業文一覧")

with session() as conn:
    jobs = get_jobs_with_latest_application(conn)

if not jobs:
    st.info("まだ案件が登録されていません。")
    st.stop()

df = pd.DataFrame(jobs)

with st.expander("🔍 絞り込み条件", expanded=False):
    c1, c2 = st.columns(2)
    prep_filter = c1.multiselect("応募準備ステータス", options=PREPARATION_STATUSES)
    generated_only = c2.selectbox("生成状況", options=["すべて", "生成済みのみ", "未生成のみ"])

filtered = df.copy()
if prep_filter:
    filtered = filtered[filtered["preparation_status"].isin(prep_filter)]
if generated_only == "生成済みのみ":
    filtered = filtered[filtered["draft_id"].notna()]
elif generated_only == "未生成のみ":
    filtered = filtered[filtered["draft_id"].isna()]

st.caption(f"{len(filtered)}件 / 全{len(df)}件")

display_df = filtered.copy()
display_df["営業文作成状況"] = display_df["draft_id"].apply(lambda v: "作成済み" if pd.notna(v) else "未作成")
display_df["コピー済み"] = display_df["copied_at"].apply(lambda v: "済" if pd.notna(v) and v else "-")

show_cols = [
    "id", "title", "application_priority" if "application_priority" in display_df.columns else "title",
    "営業文作成状況", "preparation_status", "generation_type", "tone", "proposed_price",
    "proposed_delivery_days", "コピー済み", "draft_updated_at", "url",
]
show_cols = [c for c in dict.fromkeys(show_cols) if c in display_df.columns]

st.dataframe(
    display_df[show_cols], width="stretch", hide_index=True,
    column_config={
        "id": "案件ID", "title": "案件タイトル", "preparation_status": "応募準備ステータス",
        "generation_type": "生成方式", "tone": "営業文タイプ", "proposed_price": st.column_config.NumberColumn("提案金額"),
        "proposed_delivery_days": st.column_config.NumberColumn("提案納期(日)"),
        "draft_updated_at": "最終更新日時", "url": st.column_config.LinkColumn("案件URL", display_text="開く"),
    },
)

st.divider()
st.subheader("🔎 営業文の詳細・編集")

id_to_title = dict(zip(filtered["id"], filtered["title"]))
if not id_to_title:
    st.info("表示できる案件がありません。")
    st.stop()

detail_job_id = st.selectbox(
    "案件を選択", options=list(id_to_title.keys()), format_func=lambda i: f"[{i}] {id_to_title.get(i, '')}",
    key="detail_job_id",
)

with session() as conn:
    drafts = list_application_drafts(conn, int(detail_job_id))

if not drafts:
    st.info("この案件の営業文はまだ生成されていません。「営業文生成」ページから作成してください。")
    st.stop()

draft = drafts[0]

st.markdown(f"**応募準備ステータス**: {draft.get('preparation_status')} / **生成方式**: {draft.get('generation_type')} / **トーン**: {draft.get('tone')}")
if draft.get("analysis_error"):
    st.warning(draft["analysis_error"])
for w in (draft.get("warnings") or []):
    st.warning(w)

m1, m2, m3, m4 = st.columns(4)
m1.metric("提案金額", f"{draft.get('proposed_price')}円" if draft.get("proposed_price") is not None else "-")
m2.metric("提案納期", f"{draft.get('proposed_delivery_days')}日" if draft.get("proposed_delivery_days") is not None else "-")
m3.metric("文字数", len(draft.get("application_message") or ""))
m4.metric("信頼度(confidence)", draft.get("confidence_score") if draft.get("confidence_score") is not None else "-")

edit_col, preview_col = st.columns([2, 1])

with edit_col:
    with st.form("edit_message_form"):
        edited_message = st.text_area("営業文（全文・直接編集可能）", value=draft.get("application_message") or "", height=350)
        edited_short = st.text_area("短縮版営業文", value=draft.get("short_message") or "", height=120)
        if st.form_submit_button("直接編集を保存する", type="primary"):
            with session() as conn:
                manual_edit_application(conn, draft["id"], edited_message, edited_short)
            st.success("編集内容を保存しました（再生成では上書きされません）。")
            st.rerun()

with preview_col:
    st.markdown("**関連ポートフォリオ**")
    for pid in (draft.get("selected_portfolio_ids") or []):
        st.write(f"- ポートフォリオID: {pid}")
    st.markdown("**クライアントの質問への回答**")
    for a in (draft.get("answers_to_client_questions") or []):
        st.write(f"・{a}")
    st.markdown("**事前に確認したい内容**")
    for q in (draft.get("questions_for_client") or []):
        st.write(f"・{q}")

st.markdown("#### コピー")
copy_cols = st.columns(3)
with copy_cols[0]:
    st.markdown("営業文（全文）")
    st.code(draft.get("application_message") or "", language=None)
with copy_cols[1]:
    st.markdown("短縮版営業文")
    st.code(draft.get("short_message") or "", language=None)
with copy_cols[2]:
    st.markdown("応募内容全体（JSON）")
    import json as _json
    st.code(_json.dumps({
        "application_message": draft.get("application_message"),
        "proposed_price": draft.get("proposed_price"),
        "proposed_delivery_days": draft.get("proposed_delivery_days"),
        "selected_portfolio_ids": draft.get("selected_portfolio_ids"),
    }, ensure_ascii=False, indent=2), language="json")

if st.button("コピー済みとして記録する", key=f"mark_copied_{draft['id']}"):
    with session() as conn:
        copy_application(conn, draft["id"])
    st.success("コピー日時を記録しました（応募済みへの変更は別途行ってください）。")
    st.rerun()

st.markdown("#### 営業文の編集・再生成")
instruction = st.selectbox("編集指示", options=["(選択してください)"] + list(EDIT_INSTRUCTION_MAP.keys()))
if st.button("指示を適用して再生成する", disabled=(instruction == "(選択してください)")):
    try:
        with session() as conn:
            edit_with_instruction(conn, int(detail_job_id), instruction)
        st.success(f"「{instruction}」を適用して再生成しました。")
        st.rerun()
    except GenerationBlockedError as e:
        st.error("危険案件と判定されたため再生成できません: " + " / ".join(e.reasons))
    except Exception:
        logger.exception("編集指示の適用に失敗しました。")
        st.error("再生成中にエラーが発生しました。")

action_cols = st.columns(4)
if action_cols[0].button("再生成する（内容を維持）", key=f"regen_{draft['id']}"):
    try:
        with session() as conn:
            generate_for_job(conn, int(detail_job_id), tone=draft.get("tone"), length_type=draft.get("length_type") or "標準", force_regenerate=True)
        st.success("再生成しました。")
        st.rerun()
    except GenerationBlockedError as e:
        st.error("危険案件と判定されたため再生成できません: " + " / ".join(e.reasons))

if action_cols[1].button("応募準備完了に変更", key=f"ready_{draft['id']}"):
    with session() as conn:
        update_application_draft(conn, draft["id"], {"preparation_status": "応募準備完了"})
    st.success("応募準備完了に変更しました。")
    st.rerun()

if action_cols[2].button("応募済みに変更", key=f"applied_{draft['id']}"):
    with session() as conn:
        update_application_draft(conn, draft["id"], {"preparation_status": PREP_STATUS_APPLIED})
        update_status_bulk(conn, [int(detail_job_id)], "応募済み")
    st.success("応募済みに変更しました。")
    st.rerun()

if action_cols[3].button("見送りに変更", key=f"skip_{draft['id']}"):
    with session() as conn:
        update_application_draft(conn, draft["id"], {"preparation_status": "見送り"})
        update_status_bulk(conn, [int(detail_job_id)], STATUS_SKIPPED)
    st.success("見送りに変更しました。")
    st.rerun()

st.markdown("#### 編集履歴")
with session() as conn:
    history = get_version_history(conn, draft["id"])

if history:
    for v in history:
        with st.expander(f"バージョン{v['version_number']}（{v.get('version_type')} / {v.get('created_at')}）"):
            st.text(v.get("application_message") or "")
            if st.button("このバージョンへ戻す", key=f"revert_{v['id']}"):
                with session() as conn:
                    revert_to_version(conn, draft["id"], v["id"])
                st.success("このバージョンへ戻しました。")
                st.rerun()
else:
    st.write("編集履歴はまだありません。")
