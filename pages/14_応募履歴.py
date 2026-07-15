"""応募履歴ページ: 正式に記録した応募内容の一覧・検索・詳細確認・返信/面談/条件相談/結果/フォローアップ管理。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.config import (
    AGREEMENT_STATUSES,
    APPLICATION_STATUSES,
    CONTRACT_TYPES,
    FOLLOW_UP_TYPES,
    GENERATION_TONES,
    MEETING_TYPES,
    REJECTION_REASONS,
    RESPONSE_STATUSES,
    RESPONSE_TYPES,
    SOURCE_PLATFORMS,
    URGENCY_LEVELS,
)
from src.crm.application_history_service import (
    change_application_status,
    get_application_detail,
    list_application_history,
    withdraw_application_record,
)
from src.crm.follow_up_service import complete_task, create_task
from src.crm.interview_service import (
    cancel_interview,
    complete_interview,
    confirm_interview,
    create_interview,
    get_interviews_for_record,
)
from src.crm.negotiation_service import save_negotiation
from src.crm.response_service import answer_response, get_responses_for_record, record_response, update_response_status
from src.crm.result_service import record_hired, record_rejected, record_withdrawn
from src.crm.timeline_service import add_event
from src.database import init_db, session
from src.logger import get_logger
from src.repositories import update_application_record

st.set_page_config(page_title="応募履歴 | クラウドワークス案件管理ツール", page_icon="🗂️", layout="wide")
logger = get_logger()
init_db()

st.title("🗂️ 応募履歴")
st.caption(
    "正式に応募として記録した案件の一覧・検索・詳細確認ができます。"
    "応募時点の営業文・分析結果はスナップショットとして保存され、後から変わりません。"
)

with session() as conn:
    history = list_application_history(conn)

if not history:
    st.info("まだ応募履歴がありません。「本日の営業」ページから応募を記録すると、ここに表示されます。")
    st.stop()

df = pd.DataFrame(history)

# ============================= 絞り込み =============================
with st.expander("🔍 絞り込み条件", expanded=False):
    c1, c2, c3, c4 = st.columns(4)
    date_from = c1.text_input("応募期間（開始）", placeholder="2026-07-01")
    date_to = c2.text_input("応募期間（終了）", placeholder="2026-07-31")
    platform_filter = c3.multiselect("応募経路", options=SOURCE_PLATFORMS)
    status_filter = c4.multiselect("現在ステータス", options=APPLICATION_STATUSES)

    c5, c6, c7, c8 = st.columns(4)
    category_options = sorted([c for c in df["job_category"].dropna().unique().tolist()]) if "job_category" in df.columns else []
    category_filter = c5.multiselect("ジャンル", options=category_options)
    min_price = c6.number_input("金額下限", min_value=0, value=0, step=1000)
    max_price = c7.number_input("金額上限", min_value=0, value=0, step=1000)
    tone_filter = c8.multiselect("営業文タイプ", options=GENERATION_TONES)

    c9, c10, c11 = st.columns(3)
    client_name_filter = c9.text_input("クライアント名")
    reply_filter = c10.selectbox("返信", options=["すべて", "返信あり", "返信なし"])
    interview_filter = c11.selectbox("面談", options=["すべて", "面談あり", "面談なし"])

filtered = df.copy()
if date_from:
    filtered = filtered[filtered["applied_at"].fillna("") >= date_from]
if date_to:
    filtered = filtered[filtered["applied_at"].fillna("") <= date_to + " 23:59:59"]
if platform_filter:
    filtered = filtered[filtered["source_platform"].isin(platform_filter)]
if status_filter:
    filtered = filtered[filtered["application_status"].isin(status_filter)]
if category_filter:
    filtered = filtered[filtered["job_category"].isin(category_filter)]
if min_price:
    filtered = filtered[filtered["proposed_price"].fillna(0) >= min_price]
if max_price:
    filtered = filtered[filtered["proposed_price"].fillna(10**9) <= max_price]
if tone_filter:
    filtered = filtered[filtered["tone"].isin(tone_filter)]
if client_name_filter:
    filtered = filtered[filtered["job_client_name"].fillna("").str.contains(client_name_filter, case=False, na=False)]

with session() as conn:
    ids_with_response = {rid for rid in filtered["id"].tolist() if get_responses_for_record(conn, rid)}
    ids_with_interview = {rid for rid in filtered["id"].tolist() if get_interviews_for_record(conn, rid)}

if reply_filter == "返信あり":
    filtered = filtered[filtered["id"].isin(ids_with_response)]
elif reply_filter == "返信なし":
    filtered = filtered[~filtered["id"].isin(ids_with_response)]
if interview_filter == "面談あり":
    filtered = filtered[filtered["id"].isin(ids_with_interview)]
elif interview_filter == "面談なし":
    filtered = filtered[~filtered["id"].isin(ids_with_interview)]

st.caption(f"{len(filtered)}件 / 全{len(df)}件")

display_df = filtered.copy()
display_df["返信状況"] = display_df["id"].apply(lambda i: "あり" if i in ids_with_response else "なし")
display_df["面談状況"] = display_df["id"].apply(lambda i: "あり" if i in ids_with_interview else "なし")

show_cols = [
    "applied_at", "job_title", "source_platform", "job_category", "proposed_price",
    "proposed_delivery_days", "application_status", "返信状況", "面談状況", "next_action_due_at",
    "job_client_name", "job_url",
]
show_cols = [c for c in show_cols if c in display_df.columns]

st.dataframe(
    display_df[show_cols], width="stretch", hide_index=True,
    column_config={
        "applied_at": "応募日時", "job_title": "案件タイトル", "source_platform": "応募経路",
        "job_category": "ジャンル", "proposed_price": st.column_config.NumberColumn("応募金額"),
        "proposed_delivery_days": st.column_config.NumberColumn("提案納期(日)"),
        "application_status": "現在ステータス", "next_action_due_at": "次回対応日",
        "job_client_name": "クライアント名", "job_url": st.column_config.LinkColumn("案件URL", display_text="開く"),
    },
)

st.divider()
st.subheader("📌 応募詳細")

id_to_label = {r["id"]: f"[{r['id']}] {r['job_title']}（{r['applied_at']}）" for r in filtered.to_dict("records")}
if not id_to_label:
    st.info("表示できる応募履歴がありません。")
    st.stop()

record_id = st.selectbox("応募履歴を選択", options=list(id_to_label.keys()), format_func=lambda i: id_to_label[i])

with session() as conn:
    detail = get_application_detail(conn, record_id)

record = detail["record"]
job = detail["job"]

st.markdown(f"### {job['title'] if job else record.get('job_snapshot', {}).get('title', '')}")
st.markdown(
    f"**現在ステータス**: {record['application_status']} / "
    f"**応募経路**: {record.get('source_platform')} / **応募日時**: {record['applied_at']}"
)

tabs = st.tabs([
    "応募内容", "送信した営業文", "ポートフォリオ", "AI分析スナップショット", "返信", "面談",
    "条件相談", "結果", "フォローアップ", "タイムライン", "メモ",
])

# --- 応募内容 ---
with tabs[0]:
    m1, m2, m3 = st.columns(3)
    m1.metric("応募金額", f"{record.get('proposed_price')}円" if record.get("proposed_price") is not None else "-")
    m2.metric("提案納期", f"{record.get('proposed_delivery_days')}日" if record.get("proposed_delivery_days") is not None else "-")
    m3.metric("契約種別", record.get("contract_type") or "-")
    st.write(f"税区分: {record.get('tax_type') or '-'} / 提案納品日: {record.get('proposed_delivery_date') or '-'}")
    if record.get("is_reapplication"):
        st.info(f"意図的な再応募として記録されています。理由: {record.get('reapplication_reason')}")

    st.markdown("#### ステータス変更")
    status_index = APPLICATION_STATUSES.index(record["application_status"]) if record["application_status"] in APPLICATION_STATUSES else 0
    new_status = st.selectbox("新しいステータス", options=APPLICATION_STATUSES, index=status_index, key=f"status_{record_id}")
    change_reason = st.text_input("変更理由（任意）", key=f"status_reason_{record_id}")
    if st.button("ステータスを変更する", key=f"change_status_{record_id}"):
        with session() as conn:
            result = change_application_status(conn, record_id, new_status, change_reason=change_reason or None)
        if result["requires_confirmation"]:
            st.warning(f"重要なステータス変更です（{new_status}）。案件のステータスも連動して更新されました。")
        st.success("ステータスを変更しました。")
        st.rerun()

    st.markdown("#### ステータス変更履歴")
    for h in detail["status_history"]:
        line = f"- {h['changed_at']}: {h.get('previous_status') or '(新規)'} → {h['new_status']}"
        if h.get("change_reason"):
            line += f"（{h['change_reason']}）"
        st.write(line)

    st.markdown("#### 応募記録の無効化")
    st.caption("削除は行わず無効化します（一覧から見えなくなりますが、記録自体は残ります。元に戻す操作ではありません）。")
    if st.button("この応募記録を無効化する", key=f"deactivate_{record_id}"):
        with session() as conn:
            withdraw_application_record(conn, record_id)
        st.success("応募記録を無効化しました。")
        st.rerun()

# --- 送信した営業文 ---
with tabs[1]:
    st.text_area("営業文（全文）", value=record.get("sent_message") or "", height=300, disabled=True)
    st.text_area("短縮版営業文", value=record.get("sent_short_message") or "", height=100, disabled=True)
    st.caption(f"生成方式: {record.get('generation_type') or '-'} / トーン: {record.get('tone') or '-'}")
    st.info("この内容は応募時点のスナップショットです。以降に営業文を編集・再生成しても、この表示内容は変わりません。")

# --- ポートフォリオ ---
with tabs[2]:
    portfolios = record.get("portfolio_snapshot") or []
    if not portfolios:
        st.write("選択されたポートフォリオはありませんでした。")
    for p in portfolios:
        st.write(f"- {p.get('title')}")
        if p.get("portfolio_url"):
            st.write(f"  URL: {p['portfolio_url']}")
        if p.get("github_url"):
            st.write(f"  GitHub: {p['github_url']}")

# --- AI分析スナップショット ---
with tabs[3]:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("総合スコア", record.get("total_score_snapshot") if record.get("total_score_snapshot") is not None else "-")
    m2.metric("AI適合度", record.get("ai_score_snapshot") if record.get("ai_score_snapshot") is not None else "-")
    m3.metric("安全度", record.get("safety_score_snapshot") if record.get("safety_score_snapshot") is not None else "-")
    m4.metric("デイリー優先スコア", record.get("daily_priority_score_snapshot") if record.get("daily_priority_score_snapshot") is not None else "-")
    st.write(f"応募時の応募人数: {record.get('applicant_count_snapshot') if record.get('applicant_count_snapshot') is not None else '-'}")
    st.markdown("**クライアントスナップショット**")
    st.json(record.get("client_snapshot") or {})
    st.markdown("**案件スナップショット**")
    st.json(record.get("job_snapshot") or {})

# --- 返信 ---
with tabs[4]:
    responses = detail["responses"]
    st.markdown("#### 返信を登録する")
    with st.form(f"response_form_{record_id}"):
        r_type = st.selectbox("返信種別", options=RESPONSE_TYPES)
        r_body = st.text_area("返信本文")
        r_summary = st.text_input("返信要約（任意）")
        r_urgency = st.selectbox("緊急度", options=URGENCY_LEVELS, index=1)
        r_hours = st.number_input("返信目標時間(時間)", min_value=1, value=24)
        if st.form_submit_button("返信を登録する", type="primary"):
            with session() as conn:
                record_response(
                    conn, record_id, r_type, r_body, response_summary=r_summary or None,
                    urgency=r_urgency, target_hours=int(r_hours),
                )
            st.success("返信を登録しました。")
            st.rerun()

    st.markdown("#### 返信一覧")
    for r in responses:
        with st.expander(f"{r['received_at']} - {r.get('response_type')}（対応状況: {r.get('response_status')}）"):
            st.write(r.get("response_body") or "")
            if r.get("response_due_at"):
                st.caption(f"回答期限: {r['response_due_at']}")
            if r.get("answer_body"):
                st.markdown(f"**回答内容**: {r['answer_body']}（{r.get('answered_at')}）")
            else:
                answer_text = st.text_area("回答内容", key=f"answer_{r['id']}")
                if st.button("回答を記録する", key=f"answer_btn_{r['id']}"):
                    with session() as conn:
                        answer_response(conn, r["id"], answer_text)
                    st.success("回答を記録しました。")
                    st.rerun()
            status_index = RESPONSE_STATUSES.index(r.get("response_status")) if r.get("response_status") in RESPONSE_STATUSES else 0
            new_r_status = st.selectbox("対応状況", options=RESPONSE_STATUSES, index=status_index, key=f"rstatus_{r['id']}")
            if st.button("対応状況を更新する", key=f"rstatus_btn_{r['id']}"):
                with session() as conn:
                    update_response_status(conn, r["id"], new_r_status)
                st.success("更新しました。")
                st.rerun()

# --- 面談 ---
with tabs[5]:
    interviews = detail["interviews"]
    st.markdown("#### 面談を追加する")
    with st.form(f"interview_form_{record_id}"):
        i_title = st.text_input("面談タイトル")
        i_start = st.text_input("面談予定日時", placeholder="2026-07-20 14:00:00")
        i_end = st.text_input("終了予定日時（任意）", placeholder="2026-07-20 15:00:00")
        i_type = st.selectbox("面談形式", options=MEETING_TYPES)
        i_url = st.text_input("面談URL（任意。公開画面には表示されません）")
        i_contact = st.text_input("担当者名（任意）")
        if st.form_submit_button("面談を追加する", type="primary"):
            with session() as conn:
                create_interview(
                    conn, record_id, title=i_title or None, scheduled_start=i_start or None,
                    scheduled_end=i_end or None, meeting_type=i_type, meeting_url=i_url or None,
                    contact_name=i_contact or None,
                )
            st.success("面談を追加しました。")
            st.rerun()

    for iv in interviews:
        with st.expander(f"{iv.get('scheduled_start')} - {iv.get('title') or '面談'}（{iv.get('status')}）"):
            st.write(f"形式: {iv.get('meeting_type')} / 担当者: {iv.get('contact_name') or '-'}")
            if iv.get("meeting_url"):
                st.caption("面談URLは登録済みです。")
            c1, c2, c3 = st.columns(3)
            if c1.button("確定する", key=f"confirm_iv_{iv['id']}"):
                with session() as conn:
                    confirm_interview(conn, iv["id"])
                st.rerun()
            if c2.button("キャンセルする", key=f"cancel_iv_{iv['id']}"):
                with session() as conn:
                    cancel_interview(conn, iv["id"])
                st.rerun()
            if c3.button("無断キャンセルにする", key=f"noshow_iv_{iv['id']}"):
                with session() as conn:
                    cancel_interview(conn, iv["id"], no_show=True)
                st.rerun()

            result_text = st.text_area("面談結果", value=iv.get("result") or "", key=f"result_{iv['id']}")
            next_step = st.text_input("次のステップ", value=iv.get("next_step") or "", key=f"next_step_{iv['id']}")
            if st.button("面談結果を保存して完了にする", key=f"complete_iv_{iv['id']}"):
                with session() as conn:
                    complete_interview(conn, iv["id"], result=result_text or None, next_step=next_step or None)
                st.success("面談を完了として記録しました。")
                st.rerun()

# --- 条件相談 ---
with tabs[6]:
    negotiation = detail["negotiation"] or {}
    with st.form(f"negotiation_form_{record_id}"):
        n1, n2, n3 = st.columns(3)
        original_price = n1.number_input("当初応募金額", min_value=0, value=int(negotiation.get("original_price") or record.get("proposed_price") or 0))
        client_offered_price = n2.number_input("クライアント提示金額", min_value=0, value=int(negotiation.get("client_offered_price") or 0))
        agreed_price = n3.number_input("最終合意金額", min_value=0, value=int(negotiation.get("agreed_price") or 0))

        n4, n5, n6 = st.columns(3)
        original_delivery_date = n4.text_input("当初納期", value=negotiation.get("original_delivery_date") or "")
        requested_delivery_date = n5.text_input("クライアント希望納期", value=negotiation.get("requested_delivery_date") or "")
        agreed_delivery_date = n6.text_input("最終合意納期", value=negotiation.get("agreed_delivery_date") or "")

        revision_count = st.number_input("修正回数", min_value=0, value=int(negotiation.get("revision_count") or 0))
        payment_terms = st.text_input("支払い条件", value=negotiation.get("payment_terms") or "")
        external_cost_terms = st.text_input("API・サーバー・素材費の扱い", value=negotiation.get("external_cost_terms") or "")
        maintenance_terms = st.text_input("保守対応", value=negotiation.get("maintenance_terms") or "")
        status_index = AGREEMENT_STATUSES.index(negotiation.get("agreement_status")) if negotiation.get("agreement_status") in AGREEMENT_STATUSES else 0
        agreement_status = st.selectbox("条件合意状況", options=AGREEMENT_STATUSES, index=status_index)
        negotiation_memo = st.text_area("条件相談メモ", value=negotiation.get("memo") or "")

        if st.form_submit_button("条件相談を保存する", type="primary"):
            with session() as conn:
                save_negotiation(conn, record_id, {
                    "original_price": int(original_price) or None, "client_offered_price": int(client_offered_price) or None,
                    "agreed_price": int(agreed_price) or None, "original_delivery_date": original_delivery_date or None,
                    "requested_delivery_date": requested_delivery_date or None, "agreed_delivery_date": agreed_delivery_date or None,
                    "revision_count": int(revision_count) or None, "payment_terms": payment_terms or None,
                    "external_cost_terms": external_cost_terms or None, "maintenance_terms": maintenance_terms or None,
                    "agreement_status": agreement_status, "memo": negotiation_memo or None,
                })
            st.success("条件相談を保存しました。")
            st.rerun()

# --- 結果 ---
with tabs[7]:
    results = detail["results"]
    if results:
        latest = results[0]
        st.write(f"結果種別: {latest.get('result_type')} / 日付: {latest.get('result_date')}")
        st.json({k: v for k, v in latest.items() if k not in ("id", "application_record_id", "created_at", "updated_at")})
    else:
        st.write("まだ結果は記録されていません。")

    st.markdown("#### 採用として記録する")
    with st.form(f"hired_form_{record_id}"):
        contract_amount = st.number_input("契約金額", min_value=0, value=0)
        contract_type_h = st.selectbox("契約方式", options=CONTRACT_TYPES, key=f"ct_{record_id}")
        continuation = st.selectbox("今後の継続可能性", options=["不明", "高い", "普通", "低い"])
        is_recurring = st.checkbox("継続案件か")
        hired_memo = st.text_area("メモ", key=f"hired_memo_{record_id}")
        if st.form_submit_button("採用として記録する", type="primary"):
            with session() as conn:
                record_hired(
                    conn, record_id, contract_amount=int(contract_amount) or None, contract_type=contract_type_h,
                    continuation_possible=continuation, is_recurring=is_recurring, memo=hired_memo or None,
                )
            st.success("採用として記録しました。")
            st.rerun()

    st.markdown("#### 不採用として記録する")
    with st.form(f"rejected_form_{record_id}"):
        client_reason = st.selectbox("不採用理由", options=REJECTION_REASONS)
        improvement = st.text_area("改善点（任意）")
        rejected_memo = st.text_area("メモ", key=f"rejected_memo_{record_id}")
        if st.form_submit_button("不採用として記録する"):
            with session() as conn:
                record_rejected(
                    conn, record_id, client_reason=client_reason,
                    improvement_points=[improvement] if improvement else [], memo=rejected_memo or None,
                )
            st.success("不採用として記録しました。")
            st.rerun()

    st.markdown("#### 辞退として記録する")
    with st.form(f"withdrawn_form_{record_id}"):
        withdrawal_reason = st.text_input("辞退理由")
        withdrawn_memo = st.text_area("メモ", key=f"withdrawn_memo_{record_id}")
        if st.form_submit_button("辞退として記録する"):
            with session() as conn:
                record_withdrawn(conn, record_id, withdrawal_reason=withdrawal_reason or None, memo=withdrawn_memo or None)
            st.success("辞退として記録しました。")
            st.rerun()

# --- フォローアップ ---
with tabs[8]:
    tasks = detail["follow_ups"]
    with st.form(f"followup_form_{record_id}"):
        due_at = st.text_input("次回確認日", placeholder="2026-07-25 10:00:00")
        task_type = st.selectbox("フォローアップ種別", options=FOLLOW_UP_TYPES)
        task_content = st.text_area("フォローアップ内容")
        if st.form_submit_button("フォローアップを追加する", type="primary"):
            with session() as conn:
                create_task(conn, record_id, due_at, task_type, task_content=task_content or None)
            st.success("フォローアップを追加しました。")
            st.rerun()

    for t in tasks:
        c1, c2 = st.columns([4, 1])
        c1.write(f"{t['due_at']} - {t['task_type']}: {t.get('task_content') or ''}（{t['status']}）")
        if t["status"] != "完了" and c2.button("完了にする", key=f"complete_task_{t['id']}"):
            with session() as conn:
                complete_task(conn, t["id"])
            st.rerun()

# --- タイムライン ---
with tabs[9]:
    for ev in detail["timeline"]:
        st.write(f"**{ev['event_at']}** {ev['event_type']}: {ev.get('event_title') or ''}")
        if ev.get("event_detail"):
            st.caption(ev["event_detail"])

# --- メモ ---
with tabs[10]:
    memo_text = st.text_area("ユーザーメモ", value=record.get("user_memo") or "", height=200, key=f"memo_{record_id}")
    if st.button("メモを保存する", key=f"save_memo_{record_id}"):
        with session() as conn:
            update_application_record(conn, record_id, {"user_memo": memo_text})
            add_event(conn, record_id, "メモ追加", event_title="メモを更新しました")
        st.success("メモを保存しました。")
        st.rerun()
