"""応募目標設定画面: 1日あたりの応募目標・上限・ジャンル配分・応募条件・デイリー優先スコアの重みを設定する。"""
from __future__ import annotations

import datetime as dt

import streamlit as st

from src.config import RISK_LEVEL_LABELS_JA, RISK_LEVELS
from src.daily.category_allocator import validate_allocation
from src.daily.goal_service import (
    ensure_daily_goal,
    get_default_goal_settings,
    get_score_weights,
    save_daily_goal,
    save_default_goal_settings,
    save_score_weights,
    today_jst_str,
)
from src.database import init_db, session
from src.logger import get_logger

st.set_page_config(page_title="応募目標設定 | クラウドワークス案件管理ツール", page_icon="🎯", layout="wide")
logger = get_logger()
init_db()

st.title("🎯 応募目標設定")
st.caption("ここで設定した内容は、まだ目標が作成されていない日付に対する既定値として使われます。")

with session() as conn:
    settings = get_default_goal_settings(conn)
    weights = get_score_weights(conn)

st.subheader("1日の応募目標・上限")
with st.form("goal_form"):
    c1, c2 = st.columns(2)
    target_count = c1.number_input("1日の応募目標（件）", min_value=0, value=int(settings["target_count"]))
    maximum_count = c2.number_input("1日の応募上限（件）", min_value=0, value=int(settings["maximum_count"]))
    if maximum_count < target_count:
        st.warning("応募上限が応募目標を下回っています。上限は目標以上に設定することを推奨します。")

    st.markdown("#### ジャンル別件数（AI・開発／デザイン／その他）")
    d1, d2, d3 = st.columns(3)
    ai_dev_target = d1.number_input("AI・開発（件）", min_value=0, value=int(settings["ai_development_target"]))
    design_target = d2.number_input("デザイン（件）", min_value=0, value=int(settings["design_target"]))
    other_target = d3.number_input("その他（件）", min_value=0, value=int(settings["other_target"]))

    is_valid, total = validate_allocation(target_count, ai_dev_target, design_target, other_target)
    if not is_valid:
        st.warning(f"ジャンル別件数の合計（{total}件）が1日の応募目標（{target_count}件）と一致していません。")

    st.markdown("#### 応募条件")
    e1, e2, e3 = st.columns(3)
    min_total_score = e1.number_input("最低総合スコア", min_value=0, max_value=100, value=int(settings["minimum_total_score"]))
    min_ai_score = e2.number_input("最低AI適合度", min_value=0, max_value=100, value=int(settings["minimum_ai_score"]))
    min_safety_score = e3.number_input("最低安全度", min_value=0, max_value=100, value=int(settings["minimum_safety_score"]))

    f1, f2, f3 = st.columns(3)
    allowed_risk_levels = f1.multiselect(
        "許可する危険レベル", options=RISK_LEVELS,
        default=[v for v in settings.get("allowed_risk_levels", ["low", "medium"]) if v in RISK_LEVELS],
        format_func=lambda v: RISK_LEVEL_LABELS_JA.get(v, v),
    )
    new_arrival_hours = f2.number_input("新着優先期間（時間）", min_value=1, value=int(settings["new_arrival_hours"]))
    maximum_applicant_count = f3.number_input("最大応募人数", min_value=0, value=int(settings["maximum_applicant_count"]))

    minimum_client_rating = st.slider("最低クライアント評価", 0.0, 5.0, float(settings["minimum_client_rating"]), 0.1)

    st.markdown("#### 優先条件（デイリー優先スコアの加点対象）")
    h1, h2, h3 = st.columns(3)
    prioritize_verified_client = h1.checkbox("本人確認済みを優先", value=bool(settings["prioritize_verified_client"]))
    prioritize_ready_drafts = h2.checkbox("応募準備完了を最優先", value=bool(settings["prioritize_ready_drafts"]))
    prioritize_application_written = h3.checkbox("営業文作成済みを優先", value=bool(settings["prioritize_application_written"]))

    submitted = st.form_submit_button("応募目標設定を保存する", type="primary")
    if submitted:
        new_settings = {
            "target_count": int(target_count), "maximum_count": int(maximum_count),
            "ai_development_target": int(ai_dev_target), "design_target": int(design_target),
            "other_target": int(other_target), "minimum_total_score": int(min_total_score),
            "minimum_ai_score": int(min_ai_score), "minimum_safety_score": int(min_safety_score),
            "allowed_risk_levels": allowed_risk_levels or ["low", "medium"],
            "new_arrival_hours": int(new_arrival_hours),
            "maximum_applicant_count": int(maximum_applicant_count),
            "minimum_client_rating": float(minimum_client_rating),
            "prioritize_verified_client": bool(prioritize_verified_client),
            "prioritize_ready_drafts": bool(prioritize_ready_drafts),
            "prioritize_application_written": bool(prioritize_application_written),
        }
        with session() as conn:
            save_default_goal_settings(conn, new_settings)
        st.success("応募目標設定を保存しました（新しく作成される日付から反映されます）。")
        st.rerun()

st.divider()
st.subheader("デイリー優先スコアの重み")
st.caption("9項目の合計が100%になるように設定してください。")

w_labels = {
    "total_score": "総合スコア", "safety": "安全度", "freshness": "新着度",
    "deadline_proximity": "応募期限の近さ", "applicant_scarcity": "応募人数の少なさ",
    "budget": "予算評価", "client_trust": "クライアント信頼度",
    "portfolio_match": "ポートフォリオ一致度", "draft_readiness": "営業文・応募準備状況",
}
with st.form("weights_form"):
    new_weights: dict[str, int] = {}
    cols = st.columns(3)
    for i, (key, label) in enumerate(w_labels.items()):
        new_weights[key] = cols[i % 3].number_input(
            f"{label}（%）", min_value=0, max_value=100, value=int(round(weights.get(key, 0) * 100)),
        )

    total_pct = sum(new_weights.values())
    if total_pct != 100:
        st.warning(f"重みの合計が{total_pct}%です。100%になるよう調整することを推奨します。")

    if st.form_submit_button("重みを保存する", type="primary"):
        with session() as conn:
            save_score_weights(conn, {k: v / 100 for k, v in new_weights.items()})
        st.success("デイリー優先スコアの重みを保存しました。")
        st.rerun()

st.divider()
st.subheader("特定の日付の目標を直接編集する")
st.caption("既に作成済みの日付の目標のみを、既定値とは別に個別編集したい場合はこちらから変更してください。")

edit_date = st.date_input("編集する日付", value=dt.date.fromisoformat(today_jst_str()), key="edit_goal_date").isoformat()
with session() as conn:
    day_goal = ensure_daily_goal(conn, edit_date)

with st.form("daily_goal_edit_form"):
    dc1, dc2 = st.columns(2)
    day_target = dc1.number_input("この日の応募目標（件）", min_value=0, value=int(day_goal["target_count"]))
    day_max = dc2.number_input("この日の応募上限（件）", min_value=0, value=int(day_goal["maximum_count"]))

    dd1, dd2, dd3 = st.columns(3)
    day_ai_dev = dd1.number_input("AI・開発（件）", min_value=0, value=int(day_goal["ai_development_target"]), key="day_ai_dev")
    day_design = dd2.number_input("デザイン（件）", min_value=0, value=int(day_goal["design_target"]), key="day_design")
    day_other = dd3.number_input("その他（件）", min_value=0, value=int(day_goal["other_target"]), key="day_other")

    if st.form_submit_button("この日の目標を保存する", type="primary"):
        with session() as conn:
            save_daily_goal(conn, edit_date, {
                "target_count": int(day_target), "maximum_count": int(day_max),
                "ai_development_target": int(day_ai_dev), "design_target": int(day_design),
                "other_target": int(day_other),
            })
        st.success(f"{edit_date}の目標を保存しました。")
        st.rerun()
