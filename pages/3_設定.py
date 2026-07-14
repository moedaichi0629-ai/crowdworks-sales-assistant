"""設定ページ: 検索キーワード・除外キーワード・取得条件などを管理する。"""
from __future__ import annotations

import streamlit as st

from src.config import JOB_TYPES
from src.database import init_db, session
from src.logger import get_logger
from src.repositories import get_all_settings, save_setting

st.set_page_config(page_title="設定 | クラウドワークス案件管理ツール", page_icon="⚙️", layout="wide")
logger = get_logger()
init_db()

st.title("⚙️ 設定")

with session() as conn:
    settings = get_all_settings(conn)

st.subheader("検索キーワード")
st.caption("案件収集・絞り込みで使用するキーワードです。追加・削除ができます。")

search_keywords = list(settings.get("search_keywords", []))
new_search_keyword = st.text_input("キーワードを追加", key="new_search_keyword")
if st.button("追加する", key="add_search_keyword"):
    if new_search_keyword and new_search_keyword not in search_keywords:
        search_keywords.append(new_search_keyword)
        with session() as conn:
            save_setting(conn, "search_keywords", search_keywords)
        st.success(f"「{new_search_keyword}」を追加しました。")
        st.rerun()
    elif new_search_keyword in search_keywords:
        st.warning("すでに登録されているキーワードです。")

for kw in search_keywords:
    col1, col2 = st.columns([5, 1])
    col1.write(kw)
    if col2.button("削除", key=f"del_search_{kw}"):
        search_keywords.remove(kw)
        with session() as conn:
            save_setting(conn, "search_keywords", search_keywords)
        st.rerun()

st.divider()
st.subheader("除外キーワード")
st.caption("案件本文にこのキーワードが含まれる場合、絞り込みで除外候補として識別します。")

exclude_keywords = list(settings.get("exclude_keywords", []))
new_exclude_keyword = st.text_input("除外キーワードを追加", key="new_exclude_keyword")
if st.button("追加する", key="add_exclude_keyword"):
    if new_exclude_keyword and new_exclude_keyword not in exclude_keywords:
        exclude_keywords.append(new_exclude_keyword)
        with session() as conn:
            save_setting(conn, "exclude_keywords", exclude_keywords)
        st.success(f"「{new_exclude_keyword}」を追加しました。")
        st.rerun()
    elif new_exclude_keyword in exclude_keywords:
        st.warning("すでに登録されている除外キーワードです。")

for kw in exclude_keywords:
    col1, col2 = st.columns([5, 1])
    col1.write(kw)
    if col2.button("削除", key=f"del_exclude_{kw}"):
        exclude_keywords.remove(kw)
        with session() as conn:
            save_setting(conn, "exclude_keywords", exclude_keywords)
        st.rerun()

st.divider()
st.subheader("取得・応募に関する設定")

with st.form("general_settings_form"):
    min_budget = st.number_input("最低予算", min_value=0, value=int(settings.get("min_budget", 0)), step=1000)
    max_fetch_count = st.number_input("最大取得件数", min_value=1, max_value=200, value=int(settings.get("max_fetch_count", 20)))
    default_job_type = st.selectbox(
        "デフォルトの募集形式", options=JOB_TYPES,
        index=JOB_TYPES.index(settings.get("default_job_type")) if settings.get("default_job_type") in JOB_TYPES else 0,
    )
    fetch_wait_seconds = st.number_input(
        "取得時の待機秒数", min_value=1.0, max_value=60.0, value=float(settings.get("fetch_wait_seconds", 3.0)), step=0.5
    )
    daily_application_limit = st.number_input(
        "1日の将来の応募上限数", min_value=0, max_value=100, value=int(settings.get("daily_application_limit", 5))
    )
    timezone = st.text_input("タイムゾーン", value=settings.get("timezone", "Asia/Tokyo"))

    submitted = st.form_submit_button("設定を保存する", type="primary")
    if submitted:
        with session() as conn:
            save_setting(conn, "min_budget", int(min_budget))
            save_setting(conn, "max_fetch_count", int(max_fetch_count))
            save_setting(conn, "default_job_type", default_job_type)
            save_setting(conn, "fetch_wait_seconds", float(fetch_wait_seconds))
            save_setting(conn, "daily_application_limit", int(daily_application_limit))
            save_setting(conn, "timezone", timezone)
        st.success("設定を保存しました。")
