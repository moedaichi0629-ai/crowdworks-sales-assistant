"""本日の営業画面: 応募目標にもとづき自動選定された本日の候補を確認・操作する。

クラウドワークスへの自動応募・ブラウザ自動操作・応募ボタンの自動クリックは行わない。
「応募済みとして記録する」は、ユーザーが手動で応募した事実を保存する簡易記録である。
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st

from src.application.application_generator import GenerationBlockedError
from src.application.application_service import generate_for_job
from src.applications.application_limit_service import get_limit_status
from src.applications.application_record_service import OverLimitReasonRequiredError, record_application
from src.config import CATEGORY_GROUPS, PREP_STATUS_READY
from src.daily.daily_dashboard_service import (
    add_manual_candidate,
    build_dashboard,
    postpone_candidate,
    remove_candidate,
    reselect_candidates,
    save_candidate_memo,
    skip_candidate,
)
from src.daily.goal_service import today_jst_str
from src.database import init_db, session
from src.logger import get_logger
from src.repositories import get_jobs_with_latest_application, update_application_draft

st.set_page_config(page_title="本日の営業 | クラウドワークス案件管理ツール", page_icon="🎯", layout="wide")
logger = get_logger()
init_db()

st.title("🎯 本日の営業")
st.caption("設定した応募目標にもとづき、本日応募すべき案件を自動選定して表示します（自動応募は行いません）。")

target_date = st.date_input("日付", value=dt.date.fromisoformat(today_jst_str())).isoformat()

with session() as conn:
    dashboard = build_dashboard(conn, target_date)
    limit_status = get_limit_status(conn, target_date)

goal_status = dashboard["goal_status"]
candidate_status = dashboard["candidate_status"]

# ============================= 目標状況 =============================
st.subheader("📊 目標状況")
g1, g2, g3, g4 = st.columns(4)
g1.metric("本日の応募目標", f"{goal_status['target_count']}件")
g2.metric("本日の応募上限", f"{goal_status['maximum_count']}件")
g3.metric("本日の応募済み件数", f"{goal_status['applied_count']}件")
g4.metric("目標達成率", f"{goal_status['achievement_rate']}%")

g5, g6, g7, g8 = st.columns(4)
g5.metric("目標までの残り", f"{goal_status['remaining_to_target']}件")
g6.metric("上限までの残り", f"{goal_status['remaining_to_maximum']}件")
g7.metric("応募準備完了件数", f"{goal_status['ready_count']}件")
g8.metric("営業文未作成件数", f"{goal_status['no_draft_count']}件")

if goal_status["goal_achieved"]:
    st.success(f"🎉 本日の応募目標（{goal_status['target_count']}件）を達成しました！")
if goal_status["limit_reached"]:
    st.error(f"⚠️ 本日の応募上限（{goal_status['maximum_count']}件）に達しています。上限を超えて記録する場合は理由の入力が必要です。")

st.divider()

# ============================= 候補状況 =============================
st.subheader("🗂️ 候補状況")
c1, c2, c3, c4 = st.columns(4)
c1.metric("本日の候補数", candidate_status["total_candidates"])
c2.metric("AI・開発候補数", candidate_status["ai_dev_count"])
c3.metric("デザイン候補数", candidate_status["design_count"])
c4.metric("その他候補数", candidate_status["other_count"])

c5, c6, c7 = st.columns(3)
c5.metric("最優先候補数（80点以上）", candidate_status["top_priority_count"])
c6.metric("安全度注意候補数（50点未満）", candidate_status["safety_caution_count"])
c7.metric("応募期限が近い候補数", candidate_status["deadline_soon_count"])

st.divider()

# ============================= 候補再選定・手動追加 =============================
op_col1, op_col2 = st.columns(2)
with op_col1:
    st.markdown("**候補の再選定**")
    if st.button("🔄 候補を再選定する", type="primary"):
        with session() as conn:
            result = reselect_candidates(conn, target_date)
        st.success(f"再選定しました（選定{result['selected_count']}件 / 対象外{result['leftover_count']}件）。")
        st.rerun()

with op_col2:
    st.markdown("**手動で候補を追加**")
    with session() as conn:
        all_jobs = get_jobs_with_latest_application(conn)
    candidate_job_ids = {c["job_id"] for c in dashboard["candidates"] + dashboard["excluded"]}
    addable_jobs = [j for j in all_jobs if j["id"] not in candidate_job_ids]
    id_to_title = {j["id"]: j["title"] for j in addable_jobs}
    add_job_id = st.selectbox(
        "候補に追加する案件", options=[None] + list(id_to_title.keys()),
        format_func=lambda i: "(選択してください)" if i is None else f"[{i}] {id_to_title.get(i, '')}",
    )
    if st.button("候補に追加する", disabled=(add_job_id is None)):
        with session() as conn:
            add_manual_candidate(conn, target_date, add_job_id)
        st.success("候補に追加しました。")
        st.rerun()

st.divider()

# ============================= 本日の候補一覧 =============================
st.subheader("📋 本日の候補一覧")

category_filter = st.multiselect("ジャンルで絞り込み", options=CATEGORY_GROUPS)
candidates = dashboard["candidates"]
filtered_candidates = [c for c in candidates if not category_filter or c["category_group"] in category_filter]

if not filtered_candidates:
    st.info("本日の候補はまだありません。「候補を再選定する」を実行するか、応募目標設定をご確認ください。")
else:
    df = pd.DataFrame(filtered_candidates)
    df["営業文作成状況"] = df["preparation_status"].apply(lambda v: v if v else "未作成")
    df["選定理由"] = df["selection_reasons"].apply(lambda r: " / ".join(r) if r else "")
    show_cols = [
        "rank_number", "job_title", "category_group", "daily_priority_score", "candidate_status",
        "営業文作成状況", "budget_min", "budget_max", "applicant_count", "deadline", "published_at",
        "job_url", "選定理由",
    ]
    show_cols = [c for c in show_cols if c in df.columns]
    st.dataframe(
        df[show_cols], width="stretch", hide_index=True,
        column_config={
            "rank_number": "順位", "job_title": "案件タイトル", "category_group": "ジャンル",
            "daily_priority_score": st.column_config.NumberColumn("デイリー優先スコア"),
            "candidate_status": "候補ステータス", "budget_min": st.column_config.NumberColumn("予算(下限)"),
            "budget_max": st.column_config.NumberColumn("予算(上限)"), "applicant_count": "応募人数",
            "deadline": "応募期限", "published_at": "掲載日時",
            "job_url": st.column_config.LinkColumn("案件URL", display_text="開く"),
        },
    )

with st.expander("🔍 本日の候補外（対象外）を確認する"):
    excluded = dashboard["excluded"]
    if not excluded:
        st.write("対象外の案件はありません。")
    else:
        for c in excluded:
            st.markdown(f"**{c['job_title']}**（デイリー優先スコア: {c['daily_priority_score']}点）")
            for r in c.get("exclusion_reasons") or []:
                st.write(f"・{r}")

with st.expander("📮 保留中・見送り済みの案件"):
    postponed, skipped = dashboard["postponed"], dashboard["skipped"]
    st.markdown(f"**保留中**（{len(postponed)}件）")
    for c in postponed:
        st.write(f"- {c['job_title']}（{c.get('postponed_until')}まで保留）")
    st.markdown(f"**見送り済み**（{len(skipped)}件）")
    for c in skipped:
        st.write(f"- {c['job_title']}")

st.divider()

# ============================= 候補ごとの操作 =============================
st.subheader("🛠️ 候補の操作")

if not candidates:
    st.info("操作できる候補がありません。")
    st.stop()

id_to_label = {c["id"]: f"[{c['rank_number'] or '-'}位] {c['job_title']}" for c in candidates}
candidate_id = st.selectbox("操作する候補を選択", options=list(id_to_label.keys()), format_func=lambda i: id_to_label[i])
candidate = next(c for c in candidates if c["id"] == candidate_id)

st.markdown(
    f"**デイリー優先スコア**: {candidate['daily_priority_score']}点 / "
    f"**ジャンル**: {candidate['category_group']} / "
    f"**応募準備ステータス**: {candidate.get('preparation_status') or '未作成'}"
)
with st.expander("選定理由を表示"):
    for r in candidate.get("selection_reasons") or []:
        st.write(f"・{r}")

nav_cols = st.columns(3)
with nav_cols[0]:
    try:
        st.page_link("pages/10_応募前確認.py", label="✅ 応募前確認画面を開く", icon="✅")
    except Exception:
        st.caption(f"「応募前確認」ページで案件ID {candidate['job_id']} を選択してください。")
with nav_cols[1]:
    try:
        st.page_link("pages/9_営業文一覧.py", label="📝 営業文を開く", icon="📝")
    except Exception:
        st.caption(f"「営業文一覧」ページで案件ID {candidate['job_id']} を選択してください。")
with nav_cols[2]:
    try:
        st.page_link("pages/6_スキルプロフィール.py", label="🖼️ ポートフォリオを確認する", icon="🖼️")
    except Exception:
        st.caption("「スキルプロフィール」ページの「制作実績」タブをご確認ください。")

action_cols = st.columns(4)
if action_cols[0].button("営業文を生成する", key=f"gen_{candidate_id}"):
    try:
        with session() as conn:
            generate_for_job(conn, candidate["job_id"])
        st.success("営業文を生成しました。")
        st.rerun()
    except GenerationBlockedError as e:
        st.error("危険・低品質案件のため営業文を生成できません: " + " / ".join(e.reasons))

if action_cols[1].button("応募準備完了にする", key=f"ready_{candidate_id}"):
    if candidate.get("application_draft_id"):
        with session() as conn:
            update_application_draft(conn, candidate["application_draft_id"], {"preparation_status": PREP_STATUS_READY})
        st.success("応募準備完了にしました。")
        st.rerun()
    else:
        st.warning("先に営業文を生成してください。")

if action_cols[2].button("本日の候補から外す", key=f"remove_{candidate_id}"):
    with session() as conn:
        remove_candidate(conn, candidate_id)
    st.success("本日の候補から外しました。")
    st.rerun()

if action_cols[3].button("見送りにする", key=f"skip_{candidate_id}"):
    with session() as conn:
        skip_candidate(conn, candidate_id)
    st.success("見送りにしました（以降、自動選定の対象外になります）。")
    st.rerun()

postpone_col, memo_col = st.columns(2)
with postpone_col:
    postpone_date = st.date_input(
        "保留する場合の再検討日",
        value=dt.date.fromisoformat(target_date) + dt.timedelta(days=1),
        key=f"postpone_date_{candidate_id}",
    )
    if st.button("明日以降へ保留する", key=f"postpone_{candidate_id}"):
        with session() as conn:
            postpone_candidate(conn, candidate_id, postpone_date.isoformat())
        st.success(f"{postpone_date.isoformat()}まで保留しました。")
        st.rerun()

with memo_col:
    memo = st.text_area("メモ", value=candidate.get("user_memo") or "", key=f"memo_{candidate_id}")
    if st.button("メモを保存する", key=f"save_memo_{candidate_id}"):
        with session() as conn:
            save_candidate_memo(conn, candidate_id, memo)
        st.success("メモを保存しました。")
        st.rerun()

st.markdown("#### 応募済みとして記録する（簡易記録）")
with st.form(f"apply_form_{candidate_id}"):
    price = st.number_input(
        "応募金額", min_value=0, value=int(candidate.get("draft_proposed_price") or 0), step=500,
    )
    delivery_days = st.number_input(
        "提案納期(日)", min_value=0, value=int(candidate.get("draft_proposed_delivery_days") or 0), step=1,
    )
    memo_apply = st.text_area("応募時のメモ（任意）", key=f"apply_memo_{candidate_id}")
    over_limit_reason = ""
    if limit_status["limit_reached"]:
        st.warning("本日の応募上限に達しています。記録するには理由の入力が必要です。")
        over_limit_reason = st.text_input("上限を超えて記録する理由（必須）", key=f"over_limit_reason_{candidate_id}")
    submitted = st.form_submit_button("応募済みとして記録する", type="primary")

if submitted:
    try:
        with session() as conn:
            record_application(
                conn, target_date, candidate["job_id"], candidate.get("application_draft_id"),
                int(price) or None, int(delivery_days) or None, memo_apply or None, over_limit_reason or None,
            )
        st.success("応募済みとして記録しました。")
        st.rerun()
    except OverLimitReasonRequiredError as e:
        st.error(str(e))
