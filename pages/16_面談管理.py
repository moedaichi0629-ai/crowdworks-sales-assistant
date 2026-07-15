"""面談管理ページ: 面談予定・実施結果の管理。Googleカレンダーへの自動登録は行わない。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.config import MEETING_TYPES
from src.crm.application_history_service import list_application_history
from src.crm.interview_service import (
    cancel_interview,
    complete_interview,
    confirm_interview,
    create_interview,
    list_all_interviews,
    reschedule_interview,
)
from src.database import init_db, session
from src.logger import get_logger
from src.utils import now_jst_str

st.set_page_config(page_title="面談管理 | クラウドワークス案件管理ツール", page_icon="🎤", layout="wide")
logger = get_logger()
init_db()

st.title("🎤 面談管理")
st.caption("面談予定・実施結果を一元管理します（Googleカレンダーへの自動登録は行いません）。")

with session() as conn:
    history = list_application_history(conn)
    interviews = list_all_interviews(conn)

if not history:
    st.info("まだ応募履歴がありません。先に「応募履歴」ページから応募を記録してください。")
    st.stop()

today = now_jst_str()[:10]
upcoming = [i for i in interviews if i.get("scheduled_start", "") >= now_jst_str() and i.get("status") != "実施済み"]
today_list = [i for i in interviews if (i.get("scheduled_start") or "")[:10] == today]
past = [i for i in interviews if i.get("status") in ("実施済み", "キャンセル", "無断キャンセル")]


def _render_interview_table(items: list[dict]) -> None:
    if not items:
        st.write("該当する面談はありません。")
        return
    df = pd.DataFrame(items)
    show_cols = [c for c in ["scheduled_start", "job_title", "title", "meeting_type", "contact_name", "status"] if c in df.columns]
    st.dataframe(
        df[show_cols], width="stretch", hide_index=True,
        column_config={
            "scheduled_start": "面談予定日時", "job_title": "案件タイトル", "title": "面談タイトル",
            "meeting_type": "形式", "contact_name": "担当者", "status": "ステータス",
        },
    )


tab_upcoming, tab_today, tab_past, tab_add, tab_edit = st.tabs(
    ["今後の面談", "本日の面談", "過去の面談", "面談追加", "面談編集・結果登録"]
)

with tab_upcoming:
    _render_interview_table(upcoming)

with tab_today:
    _render_interview_table(today_list)

with tab_past:
    _render_interview_table(past)

with tab_add:
    id_to_label = {j["id"]: f"[{j['id']}] {j['job_title']}（{j['applied_at']}）" for j in history}
    record_id = st.selectbox("応募履歴を選択", options=list(id_to_label.keys()), format_func=lambda i: id_to_label[i], key="add_record")

    with st.form("add_interview_form"):
        title = st.text_input("面談タイトル")
        c1, c2 = st.columns(2)
        scheduled_start = c1.text_input("面談予定日時", placeholder="2026-07-20 14:00:00")
        scheduled_end = c2.text_input("終了予定日時（任意）", placeholder="2026-07-20 15:00:00")
        c3, c4 = st.columns(2)
        meeting_type = c3.selectbox("面談形式", options=MEETING_TYPES)
        contact_name = c4.text_input("担当者名（任意）")
        meeting_url = st.text_input("面談URL（任意。公開画面には表示されません）")
        preparation_notes = st.text_area("面談前に確認すること（任意）")
        proposal_notes = st.text_area("提案内容（任意）")
        self_intro_notes = st.text_area("自己紹介メモ（任意）")

        if st.form_submit_button("面談を追加する", type="primary"):
            with session() as conn:
                create_interview(
                    conn, record_id, title=title or None, scheduled_start=scheduled_start or None,
                    scheduled_end=scheduled_end or None, meeting_type=meeting_type, meeting_url=meeting_url or None,
                    contact_name=contact_name or None, preparation_notes=preparation_notes or None,
                    proposal_notes=proposal_notes or None, self_intro_notes=self_intro_notes or None,
                )
            st.success("面談を追加しました。")
            st.rerun()

with tab_edit:
    if not interviews:
        st.info("まだ面談が登録されていません。")
    else:
        interview_labels = {i["id"]: f"[{i['id']}] {i.get('job_title')} - {i.get('scheduled_start')}（{i.get('status')}）" for i in interviews}
        interview_id = st.selectbox("編集する面談を選択", options=list(interview_labels.keys()), format_func=lambda i: interview_labels[i])
        current = next(i for i in interviews if i["id"] == interview_id)

        c1, c2 = st.columns(2)
        if c1.button("確定する", key="confirm_btn"):
            with session() as conn:
                confirm_interview(conn, interview_id)
            st.success("面談を確定しました。")
            st.rerun()
        if c2.button("キャンセルする", key="cancel_btn"):
            with session() as conn:
                cancel_interview(conn, interview_id)
            st.success("面談をキャンセルしました。")
            st.rerun()

        st.markdown("#### 日程変更")
        with st.form("reschedule_form"):
            new_start = st.text_input("新しい面談予定日時", value=current.get("scheduled_start") or "")
            new_end = st.text_input("新しい終了予定日時（任意）", value=current.get("scheduled_end") or "")
            if st.form_submit_button("日程を変更する"):
                with session() as conn:
                    reschedule_interview(conn, interview_id, new_start, new_end or None)
                st.success("日程を変更しました。")
                st.rerun()

        st.markdown("#### 面談結果登録")
        with st.form("result_form"):
            result_text = st.text_area("面談結果", value=current.get("result") or "")
            next_step = st.text_input("次のステップ", value=current.get("next_step") or "")
            next_contact_due = st.text_input("次回連絡期限（任意）", value=current.get("next_contact_due_at") or "")
            interview_notes = st.text_area("面談メモ", value=current.get("interview_notes") or "")
            if st.form_submit_button("結果を保存して完了にする", type="primary"):
                with session() as conn:
                    complete_interview(
                        conn, interview_id, result=result_text or None, next_step=next_step or None,
                        next_contact_due_at=next_contact_due or None, interview_notes=interview_notes or None,
                    )
                st.success("面談結果を保存し、完了として記録しました。")
                st.rerun()
