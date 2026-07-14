"""応募前確認ページ: 案件情報・AI分析結果・応募内容を1画面でまとめて確認する。"""
from __future__ import annotations

import streamlit as st

from src.application.checklist_service import CHECKLIST_LABELS, get_checklist, save_checklist
from src.config import RISK_LEVEL_LABELS_JA
from src.database import init_db, session
from src.repositories import (
    get_jobs_with_latest_application,
    get_latest_analysis,
    list_application_drafts,
)

st.set_page_config(page_title="応募前確認 | クラウドワークス案件管理ツール", page_icon="✅", layout="wide")
init_db()

st.title("✅ 応募前確認")
st.caption("応募する前に、案件情報・分析結果・営業文の内容をまとめて確認できます。")

with session() as conn:
    jobs = get_jobs_with_latest_application(conn)

candidates = [j for j in jobs if j.get("draft_id") is not None]
if not candidates:
    st.info("営業文が生成された案件がまだありません。「営業文生成」ページから作成してください。")
    st.stop()

id_to_title = {j["id"]: j["title"] for j in candidates}
job_id = st.selectbox("案件を選択", options=list(id_to_title.keys()), format_func=lambda i: f"[{i}] {id_to_title.get(i, '')}")

with session() as conn:
    job = next(j for j in jobs if j["id"] == job_id)
    analysis = get_latest_analysis(conn, job_id)
    drafts = list_application_drafts(conn, job_id)

draft = drafts[0] if drafts else None
if draft is None:
    st.info("この案件の営業文はまだ生成されていません。")
    st.stop()

st.markdown("## 案件情報")
c1, c2, c3, c4 = st.columns(4)
c1.write(f"**タイトル**: {job.get('title')}")
c2.write(f"**予算**: {job.get('budget_text') or '-'}")
c3.write(f"**応募期限**: {job.get('deadline') or '-'}")
c4.write(f"**クライアント**: {job.get('client_name') or '-'}")
if job.get("url"):
    st.markdown(f"[案件ページを開く]({job['url']})")
with st.expander("案件本文を表示"):
    st.text(job.get("body") or "（本文情報はありません）")

st.markdown("## 案件分析")
if analysis is None:
    st.warning("この案件はまだAI分析されていません。「AI案件分析」ページから分析を実行することをおすすめします。")
else:
    a1, a2, a3, a4, a5 = st.columns(5)
    a1.metric("総合スコア", analysis.get("total_score"))
    a2.metric("AI適合度", analysis.get("ai_suitability_score") if analysis.get("ai_suitability_score") is not None else "未使用")
    a3.metric("応募優先度", analysis.get("application_priority") or "-")
    a4.metric("難易度", analysis.get("difficulty") or "-")
    a5.metric("安全度", analysis.get("safety_score"))
    risk_level = analysis.get("risk_level")
    if risk_level in ("high", "critical"):
        st.error(f"⚠️ 危険レベル: {RISK_LEVEL_LABELS_JA.get(risk_level, risk_level)}。内容を十分ご確認のうえ応募判断してください。")
    st.write("**一致スキル**: " + ("、".join(analysis.get("matched_skills") or []) or "-"))
    st.write("**不足スキル**: " + ("、".join(analysis.get("missing_skills") or []) or "-"))
    st.write("**注意点**: " + ("、".join(analysis.get("concerns") or []) or "-"))

st.markdown("## 応募内容")
st.text_area("営業文（全文）", value=draft.get("application_message") or "", height=300, disabled=True, key="confirm_message")
b1, b2, b3 = st.columns(3)
b1.metric("提案金額", f"{draft.get('proposed_price')}円" if draft.get("proposed_price") is not None else "-")
b2.metric("提案納期", f"{draft.get('proposed_delivery_days')}日" if draft.get("proposed_delivery_days") is not None else "-")
b3.metric("応募準備ステータス", draft.get("preparation_status") or "-")

st.write("**選択したポートフォリオID**: " + ("、".join(str(i) for i in (draft.get("selected_portfolio_ids") or [])) or "なし（関連実績なし）"))
st.write("**クライアント質問への回答**")
for a in (draft.get("answers_to_client_questions") or []):
    st.write(f"・{a}")
st.write("**応募前の質問（未確認事項）**")
for q in (draft.get("questions_for_client") or []):
    st.write(f"・{q}")
memo = st.text_area("ユーザー用メモ", value=draft.get("user_memo") or "")
if st.button("メモを保存する"):
    from src.repositories import update_application_draft
    with session() as conn:
        update_application_draft(conn, draft["id"], {"user_memo": memo})
    st.success("メモを保存しました。")

st.markdown("## チェック項目")
with session() as conn:
    checklist = get_checklist(conn, draft["id"])

with st.form("checklist_form"):
    values = {}
    for field, label in CHECKLIST_LABELS.items():
        values[field] = st.checkbox(label, value=checklist.get(field, False), key=f"chk_{field}")
    if st.form_submit_button("チェック内容を保存する", type="primary"):
        with session() as conn:
            all_checked = save_checklist(conn, draft["id"], values)
        if all_checked:
            st.success("すべての項目を確認しました。応募準備ステータスを「応募準備完了」に変更しました。")
        else:
            st.info("チェック内容を保存しました。")
        st.rerun()
