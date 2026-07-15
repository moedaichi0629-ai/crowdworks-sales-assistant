"""返信管理ページ: クライアントからの返信の未対応・期限確認・対応済み管理。

返信本文には個人情報が含まれる可能性があるため、外部AIへの自動送信は行わない。
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.config import DEFAULT_RESPONSE_TARGET_HOURS, RESPONSE_STATUSES, RESPONSE_TYPES, URGENCY_LEVELS
from src.crm.application_history_service import list_application_history
from src.crm.response_service import (
    answer_response,
    get_overdue_responses,
    get_responses_for_record,
    get_unhandled_responses,
    record_response,
    update_response_status,
)
from src.database import init_db, session
from src.logger import get_logger
from src.utils import now_jst_str

st.set_page_config(page_title="返信管理 | クラウドワークス案件管理ツール", page_icon="💬", layout="wide")
logger = get_logger()
init_db()

st.title("💬 返信管理")
st.caption("クライアントからの返信を記録し、対応状況・回答期限を管理します（返信本文は外部AIへ自動送信しません）。")

with session() as conn:
    history = list_application_history(conn)
    unhandled = get_unhandled_responses(conn)
    overdue = get_overdue_responses(conn)

if not history:
    st.info("まだ応募履歴がありません。先に「応募履歴」ページから応募を記録してください。")
    st.stop()

overdue_ids = {r["id"] for r in overdue}


def _render_response_table(responses: list[dict]) -> None:
    if not responses:
        st.write("該当する返信はありません。")
        return
    df = pd.DataFrame(responses)
    df["期限超過"] = df["id"].apply(lambda i: "⚠️超過" if i in overdue_ids else "")
    show_cols = [c for c in ["received_at", "job_title", "response_type", "urgency", "response_due_at", "期限超過", "response_status"] if c in df.columns]
    st.dataframe(
        df[show_cols], width="stretch", hide_index=True,
        column_config={
            "received_at": "受信日時", "job_title": "案件タイトル", "response_type": "返信種別",
            "urgency": "緊急度", "response_due_at": "回答期限", "response_status": "対応状況",
        },
    )


tab_unhandled, tab_due_soon, tab_done, tab_register = st.tabs(
    ["未対応返信", "回答期限が近い返信", "対応済み返信", "返信内容登録"]
)

with tab_unhandled:
    if overdue:
        st.error(f"⚠️ 回答期限を過ぎた未対応の返信が{len(overdue)}件あります。")
    _render_response_table(unhandled)

with tab_due_soon:
    import datetime

    from src.utils import now_jst

    now = now_jst().replace(tzinfo=None)
    soon = now + datetime.timedelta(hours=48)
    now_str, soon_str = now.strftime("%Y-%m-%d %H:%M:%S"), soon.strftime("%Y-%m-%d %H:%M:%S")
    due_soon = [
        r for r in unhandled
        if r.get("response_due_at") and now_str <= r["response_due_at"] <= soon_str
    ]
    st.caption("48時間以内に回答期限を迎える未対応の返信です。")
    _render_response_table(due_soon)

with tab_done:
    with session() as conn:
        from src.repositories import list_client_responses_by_status

        done = list_client_responses_by_status(conn, ["返信済み", "対応不要"])
    _render_response_table(done)

with tab_register:
    id_to_label = {j["id"]: f"[{j['id']}] {j['job_title']}（{j['applied_at']}）" for j in history}
    record_id = st.selectbox("応募履歴を選択", options=list(id_to_label.keys()), format_func=lambda i: id_to_label[i])

    st.markdown("#### 返信内容登録")
    with st.form("register_response_form"):
        r_type = st.selectbox("返信種別", options=RESPONSE_TYPES)
        r_body = st.text_area("返信本文")
        r_summary = st.text_input("返信要約（任意）")
        r_urgency = st.selectbox("緊急度", options=URGENCY_LEVELS, index=1)
        r_hours = st.number_input("返信目標時間(時間)", min_value=1, value=DEFAULT_RESPONSE_TARGET_HOURS)
        if st.form_submit_button("返信を登録する", type="primary"):
            with session() as conn:
                record_response(
                    conn, record_id, r_type, r_body, response_summary=r_summary or None,
                    urgency=r_urgency, target_hours=int(r_hours),
                )
            st.success("返信を登録しました。")
            st.rerun()

    st.divider()
    st.markdown("#### 回答内容登録・対応状況変更")
    with session() as conn:
        record_responses = get_responses_for_record(conn, record_id)

    if not record_responses:
        st.info("この応募履歴にはまだ返信が登録されていません。")
    for r in record_responses:
        with st.expander(f"{r['received_at']} - {r.get('response_type')}（{r.get('response_status')}）"):
            st.write(r.get("response_body") or "")
            if not r.get("answer_body"):
                answer_text = st.text_area("回答内容", key=f"ans_{r['id']}")
                if st.button("回答を記録する", key=f"ans_btn_{r['id']}"):
                    with session() as conn:
                        answer_response(conn, r["id"], answer_text)
                    st.success("回答を記録しました。")
                    st.rerun()
            else:
                st.markdown(f"**回答済み**: {r['answer_body']}（{r.get('answered_at')}）")

            status_index = RESPONSE_STATUSES.index(r.get("response_status")) if r.get("response_status") in RESPONSE_STATUSES else 0
            new_status = st.selectbox("対応状況", options=RESPONSE_STATUSES, index=status_index, key=f"status_{r['id']}")
            if st.button("対応状況を更新する", key=f"status_btn_{r['id']}"):
                with session() as conn:
                    update_response_status(conn, r["id"], new_status)
                st.success("更新しました。")
                st.rerun()
