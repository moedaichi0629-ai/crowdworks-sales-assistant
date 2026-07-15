"""フォローアップページ: 応募後に結果が出ていない案件の確認・整理タスクを管理する。自動送信は行わない。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.config import FOLLOW_UP_STATUSES, FOLLOW_UP_TYPES
from src.crm.application_history_service import list_application_history
from src.crm.follow_up_service import (
    complete_task,
    create_task,
    get_completed_tasks,
    get_overdue_tasks,
    get_today_tasks,
    get_upcoming_tasks,
    update_task_status,
)
from src.database import init_db, session
from src.logger import get_logger

st.set_page_config(page_title="フォローアップ | クラウドワークス案件管理ツール", page_icon="✅", layout="wide")
logger = get_logger()
init_db()

st.title("✅ フォローアップ")
st.caption("応募後に結果が出ていない案件へ、確認・整理のためのタスクを管理します（自動送信は行いません）。")

with session() as conn:
    history = list_application_history(conn)
    overdue = get_overdue_tasks(conn)
    today_tasks = get_today_tasks(conn)
    upcoming = get_upcoming_tasks(conn, days=7)
    completed = get_completed_tasks(conn)

if not history:
    st.info("まだ応募履歴がありません。先に「応募履歴」ページから応募を記録してください。")
    st.stop()

if overdue:
    st.error(f"⚠️ 期限を過ぎている未対応のフォローアップが{len(overdue)}件あります。")


def _render_task_table(tasks: list[dict], allow_complete: bool = True) -> None:
    if not tasks:
        st.write("該当するタスクはありません。")
        return
    df = pd.DataFrame(tasks)
    show_cols = [c for c in ["due_at", "job_title", "task_type", "task_content", "status"] if c in df.columns]
    st.dataframe(
        df[show_cols], width="stretch", hide_index=True,
        column_config={
            "due_at": "次回確認日", "job_title": "案件タイトル", "task_type": "種別",
            "task_content": "内容", "status": "対応状況",
        },
    )
    if allow_complete:
        for t in tasks:
            if t.get("status") != "完了":
                c1, c2 = st.columns([5, 1])
                c1.write(f"[{t['id']}] {t.get('job_title')} - {t['due_at']} - {t['task_type']}")
                if c2.button("完了にする", key=f"complete_{t['id']}"):
                    with session() as conn:
                        complete_task(conn, t["id"])
                    st.rerun()


tab_today, tab_overdue, tab_upcoming, tab_done, tab_add = st.tabs(
    ["本日対応", "期限超過", "今後7日間", "対応済み", "タスク追加・編集"]
)

with tab_today:
    _render_task_table(today_tasks)

with tab_overdue:
    _render_task_table(overdue)

with tab_upcoming:
    _render_task_table(upcoming)

with tab_done:
    _render_task_table(completed, allow_complete=False)

with tab_add:
    id_to_label = {j["id"]: f"[{j['id']}] {j['job_title']}（{j['applied_at']}）" for j in history}
    record_id = st.selectbox("応募履歴を選択", options=list(id_to_label.keys()), format_func=lambda i: id_to_label[i])

    with st.form("add_task_form"):
        due_at = st.text_input("次回確認日", placeholder="2026-07-25 10:00:00")
        task_type = st.selectbox("フォローアップ種別", options=FOLLOW_UP_TYPES)
        task_content = st.text_area("フォローアップ内容")
        memo = st.text_area("メモ（任意）")
        if st.form_submit_button("フォローアップを追加する", type="primary"):
            with session() as conn:
                create_task(conn, record_id, due_at, task_type, task_content=task_content or None, memo=memo or None)
            st.success("フォローアップを追加しました。")
            st.rerun()

    st.divider()
    st.markdown("#### 対応状況の変更")
    with session() as conn:
        from src.crm.follow_up_service import get_tasks_for_record

        record_tasks = get_tasks_for_record(conn, record_id)

    if not record_tasks:
        st.info("この応募履歴にはまだフォローアップがありません。")
    for t in record_tasks:
        status_index = FOLLOW_UP_STATUSES.index(t.get("status")) if t.get("status") in FOLLOW_UP_STATUSES else 0
        new_status = st.selectbox(
            f"[{t['id']}] {t['due_at']} - {t['task_type']}", options=FOLLOW_UP_STATUSES,
            index=status_index, key=f"edit_status_{t['id']}",
        )
        if st.button("更新する", key=f"edit_status_btn_{t['id']}"):
            with session() as conn:
                update_task_status(conn, t["id"], new_status)
            st.success("更新しました。")
            st.rerun()
