"""AI分析設定ページ: プロバイダー・重み・優先度境界値・危険キーワード等を設定する。"""
from __future__ import annotations

import streamlit as st

from src.ai.provider_factory import is_provider_available
from src.analysis.score_calculator import validate_weights
from src.config import (
    AI_PROVIDERS,
    DEFAULT_MODELS,
    DEFAULT_PRIORITY_THRESHOLDS,
    DEFAULT_SCORE_WEIGHTS,
)
from src.database import init_db, session
from src.logger import get_logger
from src.repositories import get_all_analysis_settings, save_analysis_setting

st.set_page_config(page_title="AI分析設定 | クラウドワークス案件管理ツール", page_icon="⚙️", layout="wide")
logger = get_logger()
init_db()

st.title("⚙️ AI分析設定")

with session() as conn:
    settings = get_all_analysis_settings(conn)

# ============================= APIキーの状態 =============================
st.subheader("APIキーの状態")
st.caption("APIキーは `.env` ファイルで管理されます。この画面にはキーの文字列自体は表示・保存しません。")
key_cols = st.columns(3)
for i, provider in enumerate(["openai", "anthropic", "gemini"]):
    with key_cols[i]:
        if is_provider_available(provider):
            st.success(f"{provider}: 設定済み")
        else:
            st.warning(f"{provider}: 未設定")

st.divider()

# ============================= プロバイダー・API設定 =============================
st.subheader("AIプロバイダー・API設定")
with st.form("provider_settings_form"):
    provider = st.selectbox(
        "AIプロバイダー", options=AI_PROVIDERS,
        index=AI_PROVIDERS.index(settings.get("ai_provider")) if settings.get("ai_provider") in AI_PROVIDERS else 0,
    )
    models = dict(settings.get("ai_models") or DEFAULT_MODELS)
    mc1, mc2, mc3 = st.columns(3)
    models["openai"] = mc1.text_input("OpenAIモデル名", value=models.get("openai", DEFAULT_MODELS["openai"]))
    models["anthropic"] = mc2.text_input("Anthropicモデル名", value=models.get("anthropic", DEFAULT_MODELS["anthropic"]))
    models["gemini"] = mc3.text_input("Geminiモデル名", value=models.get("gemini", DEFAULT_MODELS["gemini"]))

    c1, c2, c3 = st.columns(3)
    timeout = c1.number_input("APIタイムアウト（秒）", min_value=5, max_value=120, value=int(settings.get("api_timeout_seconds", 30)))
    max_retry = c2.number_input("最大再試行回数", min_value=0, max_value=5, value=int(settings.get("max_retry_count", 1)))
    max_tokens = c3.number_input("使用トークン上限", min_value=100, max_value=8000, value=int(settings.get("max_tokens", 1500)))

    c4, c5, c6 = st.columns(3)
    bulk_max = c4.number_input("一括分析上限", min_value=1, max_value=500, value=int(settings.get("bulk_analysis_max_count", 10)))
    wait_seconds = c5.number_input("分析間の待機秒数", min_value=0.0, max_value=60.0, value=float(settings.get("analysis_wait_seconds", 2.0)), step=0.5)
    daily_limit = c6.number_input("1日あたりの分析上限件数", min_value=1, max_value=1000, value=int(settings.get("daily_analysis_limit", 50)))

    rule_based_only = st.checkbox("AI分析を使わずルールベースのみで動作する", value=bool(settings.get("rule_based_only", False)))

    if st.form_submit_button("この設定を保存する", type="primary"):
        with session() as conn:
            save_analysis_setting(conn, "ai_provider", provider)
            save_analysis_setting(conn, "ai_models", models)
            save_analysis_setting(conn, "api_timeout_seconds", int(timeout))
            save_analysis_setting(conn, "max_retry_count", int(max_retry))
            save_analysis_setting(conn, "max_tokens", int(max_tokens))
            save_analysis_setting(conn, "bulk_analysis_max_count", int(bulk_max))
            save_analysis_setting(conn, "analysis_wait_seconds", float(wait_seconds))
            save_analysis_setting(conn, "daily_analysis_limit", int(daily_limit))
            save_analysis_setting(conn, "rule_based_only", rule_based_only)
        st.success("保存しました。")
        st.rerun()

st.divider()

# ============================= 総合スコアの重み =============================
st.subheader("総合スコアの重み")
st.caption("合計が100%になるようにしてください。100%にならない場合は保存前に警告を表示します。")

weight_labels = {
    "ai_suitability": "AI適合度", "rule_based": "ルールベーススコア", "safety": "安全度",
    "budget": "予算評価", "deadline": "納期の余裕", "applicant_count": "応募人数",
    "client_trust": "クライアント信頼度", "portfolio_match": "ポートフォリオ一致度",
}
current_weights = dict(settings.get("score_weights") or DEFAULT_SCORE_WEIGHTS)

with st.form("weights_form"):
    new_weights = {}
    weight_cols = st.columns(4)
    for i, (key, label) in enumerate(weight_labels.items()):
        with weight_cols[i % 4]:
            new_weights[key] = st.number_input(
                f"{label}（%）", min_value=0, max_value=100,
                value=int(round(current_weights.get(key, 0) * 100)), key=f"weight_{key}",
            ) / 100

    total_pct = sum(new_weights.values()) * 100
    st.write(f"現在の合計: **{total_pct:.0f}%**")

    if st.form_submit_button("重みを保存する", type="primary"):
        is_valid, _ = validate_weights(new_weights)
        if not is_valid:
            st.error(f"重みの合計が100%になっていません（現在: {total_pct:.0f}%）。合計が100%になるよう調整してから保存してください。")
        else:
            with session() as conn:
                save_analysis_setting(conn, "score_weights", new_weights)
            st.success("保存しました。")
            st.rerun()

st.divider()

# ============================= 優先度の境界値 =============================
st.subheader("応募優先度の境界値")
current_thresholds = dict(settings.get("priority_thresholds") or DEFAULT_PRIORITY_THRESHOLDS)
with st.form("thresholds_form"):
    t1, t2, t3, t4 = st.columns(4)
    top = t1.number_input("最優先（以上）", min_value=0, max_value=100, value=int(current_thresholds.get("top", 90)))
    high = t2.number_input("優先（以上）", min_value=0, max_value=100, value=int(current_thresholds.get("high", 80)))
    candidate = t3.number_input("応募候補（以上）", min_value=0, max_value=100, value=int(current_thresholds.get("candidate", 70)))
    review = t4.number_input("要確認（以上）", min_value=0, max_value=100, value=int(current_thresholds.get("review", 60)))

    if st.form_submit_button("境界値を保存する", type="primary"):
        if not (top >= high >= candidate >= review):
            st.error("境界値は「最優先 ≥ 優先 ≥ 応募候補 ≥ 要確認」の順になるように設定してください。")
        else:
            with session() as conn:
                save_analysis_setting(conn, "priority_thresholds", {"top": top, "high": high, "candidate": candidate, "review": review})
            st.success("保存しました。")
            st.rerun()

st.divider()

# ============================= 危険キーワード =============================
st.subheader("危険キーワード（カテゴリ別）")
st.caption("キーワードが含まれるだけで自動的に不採用にはせず、AIの文脈判定と併用されます。")
danger_categories = dict(settings.get("danger_keyword_categories") or {})

for category, keywords in danger_categories.items():
    with st.expander(category):
        text_value = st.text_area("キーワード（カンマ区切り）", value=", ".join(keywords), key=f"danger_{category}")
        if st.button("このカテゴリを保存", key=f"save_danger_{category}"):
            new_categories = dict(danger_categories)
            new_categories[category] = [k.strip() for k in text_value.split(",") if k.strip()]
            with session() as conn:
                save_analysis_setting(conn, "danger_keyword_categories", new_categories)
            st.success("保存しました。")
            st.rerun()

with st.expander("新しい危険キーワードカテゴリを追加"):
    new_cat_name = st.text_input("カテゴリ名", key="new_danger_category_name")
    new_cat_keywords = st.text_input("キーワード（カンマ区切り）", key="new_danger_category_keywords")
    if st.button("カテゴリを追加する"):
        if new_cat_name:
            new_categories = dict(danger_categories)
            new_categories[new_cat_name] = [k.strip() for k in new_cat_keywords.split(",") if k.strip()]
            with session() as conn:
                save_analysis_setting(conn, "danger_keyword_categories", new_categories)
            st.success("追加しました。")
            st.rerun()

st.divider()

# ============================= 加点・減点キーワード =============================
st.subheader("加点・減点キーワード")
bonus_keywords = list(settings.get("bonus_keywords") or [])
penalty_keywords = list(settings.get("penalty_keywords") or [])

bc1, bc2 = st.columns(2)
with bc1:
    st.markdown("**加点キーワード**")
    bonus_text = st.text_area("カンマ区切り", value=", ".join(bonus_keywords), key="bonus_keywords_text")
with bc2:
    st.markdown("**減点キーワード**")
    penalty_text = st.text_area("カンマ区切り", value=", ".join(penalty_keywords), key="penalty_keywords_text")

if st.button("加点・減点キーワードを保存する"):
    with session() as conn:
        save_analysis_setting(conn, "bonus_keywords", [k.strip() for k in bonus_text.split(",") if k.strip()])
        save_analysis_setting(conn, "penalty_keywords", [k.strip() for k in penalty_text.split(",") if k.strip()])
    st.success("保存しました。")
    st.rerun()

st.divider()

# ============================= 分析対象条件 =============================
st.subheader("「条件に合う案件」の絞り込み条件")
with st.form("target_condition_form"):
    c1, c2, c3, c4 = st.columns(4)
    min_body_chars = c1.number_input("最低限必要な案件本文文字数", min_value=0, max_value=1000, value=int(settings.get("min_body_chars_for_analysis", 20)))
    min_budget = c2.number_input("最低予算", min_value=0, value=int(settings.get("min_budget_for_analysis", 0)), step=1000)
    max_applicants = c3.number_input("最大応募人数（0で無制限）", min_value=0, value=int(settings.get("max_applicant_count", 0)))
    min_rating = c4.number_input("最低クライアント評価", min_value=0.0, max_value=5.0, value=float(settings.get("min_client_rating", 0.0)), step=0.1)

    require_identity = st.checkbox("本人確認済みの案件のみを対象とする", value=bool(settings.get("require_identity_verified", False)))

    if st.form_submit_button("条件を保存する", type="primary"):
        with session() as conn:
            save_analysis_setting(conn, "min_body_chars_for_analysis", int(min_body_chars))
            save_analysis_setting(conn, "min_budget_for_analysis", int(min_budget))
            save_analysis_setting(conn, "max_applicant_count", int(max_applicants))
            save_analysis_setting(conn, "min_client_rating", float(min_rating))
            save_analysis_setting(conn, "require_identity_verified", require_identity)
        st.success("保存しました。")
        st.rerun()
