"""営業文生成ページ: 案件を選択し、AIまたはテンプレートで営業文の下書きを作成する。"""
from __future__ import annotations

import streamlit as st

from src.ai.provider_factory import is_provider_available
from src.application.application_generator import GenerationBlockedError
from src.application.application_service import (
    generate_for_job,
    run_bulk_generation,
    select_application_target_jobs,
)
from src.application.template_generator import TEMPLATE_CATEGORIES, detect_template_category, recommend_tone
from src.config import (
    AI_PROVIDER_NONE,
    DEFAULT_APPLICATION_MODELS,
    GENERATION_TONES,
    LENGTH_TYPES,
)
from src.database import init_db, session
from src.delivery.delivery_service import get_delivery_settings, save_delivery_settings
from src.logger import get_logger
from src.pricing.pricing_service import get_pricing_settings, save_pricing_settings
from src.repositories import (
    get_all_analysis_settings,
    get_job,
    get_jobs_with_latest_analysis,
    get_profile_bundle,
    list_portfolios,
)

st.set_page_config(page_title="営業文生成 | クラウドワークス案件管理ツール", page_icon="✍️", layout="wide")
logger = get_logger()
init_db()

st.title("✍️ 営業文生成")
st.caption("AI分析結果・スキルプロフィール・制作実績をもとに、案件専用の営業文の下書きを作成します。")

with session() as conn:
    analysis_settings = get_all_analysis_settings(conn)
    jobs = get_jobs_with_latest_analysis(conn)

provider = analysis_settings.get("ai_provider", AI_PROVIDER_NONE)
app_models = analysis_settings.get("application_ai_models") or DEFAULT_APPLICATION_MODELS
app_model = app_models.get(provider)
provider_ready = is_provider_available(provider)

if provider == AI_PROVIDER_NONE:
    st.info("現在の設定: AIプロバイダー『使用しない』。テンプレートによる下書き作成のみ利用できます。")
elif not provider_ready:
    st.warning(f"AIプロバイダー『{provider}』のAPIキーが未設定のため、テンプレートによる下書き作成のみ利用できます。")
else:
    st.success(f"AIプロバイダー: {provider} / 営業文生成用モデル: {app_model or '(既定値)'}")

if not jobs:
    st.info("まだ案件が登録されていません。")
    st.stop()

tab_single, tab_bulk, tab_settings = st.tabs(["1件ずつ生成", "一括生成", "料金・納期の設定"])

# ============================= 1件ずつ生成 =============================
with tab_single:
    id_to_label = {
        j["id"]: f"[{j['id']}] {j['title']}"
        + (f"（優先度: {j['application_priority']}）" if j.get("application_priority") else "")
        for j in jobs
    }
    job_id = st.selectbox("案件を選択", options=list(id_to_label.keys()), format_func=lambda i: id_to_label[i])

    with session() as conn:
        job = get_job(conn, job_id)
        bundle = get_profile_bundle(conn)

    if job is None:
        st.warning("案件が見つかりません。")
        st.stop()

    with st.expander("案件本文を表示"):
        st.text(job.get("body") or "（本文情報はありません）")

    category = detect_template_category(job)
    default_tone = recommend_tone(category)
    st.caption(f"案件カテゴリ自動判定: **{category}** / おすすめトーン: **{default_tone}**")

    with st.form("generate_form"):
        c1, c2 = st.columns(2)
        tone = c1.selectbox("営業文タイプ（トーン）", options=GENERATION_TONES, index=GENERATION_TONES.index(default_tone))
        length_type = c2.selectbox("文章の長さ", options=LENGTH_TYPES)

        c3, c4 = st.columns(2)
        show_headings = c3.checkbox("見出しを入れる", value=False)
        force_template = c4.checkbox("AI APIを使わずテンプレートのみで生成する", value=(provider == AI_PROVIDER_NONE or not provider_ready))

        additional_message = st.text_area("追加で伝えたい内容（任意）")
        exclude_content = st.text_area("営業文に含めたくない内容（任意）")

        with session() as conn:
            portfolios = list_portfolios(conn, bundle["profile"]["id"])
        portfolio_options = {p["id"]: p["title"] for p in portfolios if p.get("is_active", True)}
        manual_portfolio_ids = st.multiselect(
            "紹介する制作実績（未選択の場合は自動選択します）",
            options=list(portfolio_options.keys()), format_func=lambda i: portfolio_options.get(i, str(i)),
        )

        c5, c6 = st.columns(2)
        price_override = c5.number_input("応募金額を指定する（0で自動提案）", min_value=0, value=0, step=500)
        delivery_override = c6.number_input("納期日数を指定する（0で自動提案）", min_value=0, value=0, step=1)

        force_regenerate = st.checkbox("強制再生成する（前回の結果を無視する）", value=False)

        submitted = st.form_submit_button("営業文を生成する", type="primary")

    if submitted:
        try:
            with session() as conn:
                result = generate_for_job(
                    conn, job_id, tone=tone, length_type=length_type, show_headings=show_headings,
                    additional_message=additional_message or None, exclude_content=exclude_content or None,
                    manual_portfolio_ids=manual_portfolio_ids or None,
                    price_override=price_override or None, delivery_days_override=delivery_override or None,
                    force_template=force_template, force_regenerate=force_regenerate,
                )
            if result.get("_from_cache"):
                st.info("前回と同じ内容のため、キャッシュされた下書きを表示しています（内容は変わりません）。")
            else:
                st.success(f"営業文を生成しました（生成方式: {result.get('generation_type')}）。詳細・編集は「営業文一覧」ページから行えます。")

            if result.get("warnings"):
                for w in result["warnings"]:
                    st.warning(w)

            st.markdown("### プレビュー")
            m1, m2, m3 = st.columns(3)
            m1.metric("提案金額", f"{result.get('proposed_price')}円" if result.get("proposed_price") is not None else "-")
            m2.metric("提案納期", f"{result.get('proposed_delivery_days')}日" if result.get("proposed_delivery_days") is not None else "-")
            m3.metric("文字数", len(result.get("application_message") or result.get("full_message") or ""))
            st.text_area("営業文（全文）", value=result.get("application_message") or result.get("full_message") or "", height=400)
        except GenerationBlockedError as e:
            st.error("⚠️ 危険・低品質案件の可能性があるため、営業文の自動生成を停止しました。")
            for r in e.reasons:
                st.warning(r)
        except ValueError as e:
            st.error(str(e))
        except Exception:
            logger.exception("営業文生成に失敗しました。")
            st.error("営業文生成中に予期しないエラーが発生しました。詳細はlogs/app.logをご確認ください。")

# ============================= 一括生成 =============================
with tab_bulk:
    target_mode = st.selectbox(
        "生成対象",
        options=["未生成案件のみ", "選択した案件", "応募候補ステータスのみ", "応募優先度が高い案件のみ", "全案件を再生成"],
        key="bulk_target_mode",
    )

    with session() as conn:
        if target_mode == "選択した案件":
            id_to_title = {j["id"]: j["title"] for j in jobs}
            selected_ids = st.multiselect(
                "対象案件", options=list(id_to_title.keys()), format_func=lambda i: f"[{i}] {id_to_title.get(i, '')}",
            )
        else:
            selected_ids = None
        bulk_targets = select_application_target_jobs(conn, target_mode, selected_ids)

    st.write(f"対象案件数: **{len(bulk_targets)}件**")

    b1, b2 = st.columns(2)
    bulk_max_count = b1.number_input(
        "一括生成件数（上限）", min_value=1, max_value=50,
        value=int(analysis_settings.get("application_bulk_max_count", 5)),
    )
    bulk_wait_seconds = b2.number_input("生成間の待機秒数", min_value=0.0, max_value=30.0, value=2.0, step=0.5)
    bulk_force_template = st.checkbox(
        "AI APIを使わずテンプレートのみで生成する", value=(provider == AI_PROVIDER_NONE or not provider_ready), key="bulk_force_template",
    )

    if st.button("一括生成を開始する", type="primary", disabled=(len(bulk_targets) == 0)):
        job_ids = [j["id"] for j in bulk_targets]
        progress_bar = st.progress(0.0, text="生成を開始します…")

        def _on_progress(done: int, total: int) -> None:
            progress_bar.progress(done / total if total else 1.0, text=f"生成中… {done}/{total}件")

        try:
            with session() as conn:
                summary = run_bulk_generation(
                    conn, job_ids, wait_seconds=float(bulk_wait_seconds), max_count=int(bulk_max_count),
                    force_template=bulk_force_template, progress_callback=_on_progress,
                )
            progress_bar.progress(1.0, text="完了しました。")
            st.success("一括生成が完了しました。")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("対象件数", summary["total"])
            m2.metric("成功件数", summary["success"])
            m3.metric("失敗件数", summary["failed"])
            m4.metric("危険案件でスキップ", summary["blocked"])
            st.info("結果は「営業文一覧」ページで確認・編集できます。")
        except Exception:
            logger.exception("営業文の一括生成に失敗しました。")
            st.error("一括生成中に予期しないエラーが発生しました。詳細はlogs/app.logをご確認ください。")

# ============================= 料金・納期の設定 =============================
with tab_settings:
    st.markdown("#### 応募金額の初期設定")
    with session() as conn:
        pricing = get_pricing_settings(conn)
        delivery = get_delivery_settings(conn)

    with st.form("pricing_form"):
        p1, p2, p3 = st.columns(3)
        base_rate = p1.number_input("基準時間単価（円）", min_value=0, value=int(pricing["base_hourly_rate_yen"]), step=100)
        ai_rate_min = p2.number_input("AI・API連携案件の時給下限（円）", min_value=0, value=int(pricing["ai_api_hourly_rate_min"]), step=100)
        ai_rate_max = p3.number_input("AI・API連携案件の時給上限（円）", min_value=0, value=int(pricing["ai_api_hourly_rate_max"]), step=100)

        p4, p5, p6 = st.columns(3)
        website_min = p4.number_input("ホームページ制作の最低金額（円）", min_value=0, value=int(pricing["website_minimum_price_yen"]), step=1000)
        min_order = p5.number_input("最低受注金額（円）", min_value=0, value=int(pricing["minimum_order_price_yen"]), step=500)
        revision_count = p6.number_input("標準修正回数", min_value=0, value=int(pricing["standard_revision_count"]))

        if st.form_submit_button("料金設定を保存する", type="primary"):
            new_pricing = {
                **pricing, "base_hourly_rate_yen": int(base_rate), "ai_api_hourly_rate_min": int(ai_rate_min),
                "ai_api_hourly_rate_max": int(ai_rate_max), "website_minimum_price_yen": int(website_min),
                "minimum_order_price_yen": int(min_order), "standard_revision_count": int(revision_count),
            }
            with session() as conn:
                save_pricing_settings(conn, new_pricing)
            st.success("料金設定を保存しました。")
            st.rerun()

    st.divider()
    st.markdown("#### 納期の初期設定")
    with st.form("delivery_form"):
        d1, d2, d3 = st.columns(3)
        daily_hours = d1.number_input("1日あたりの標準稼働時間", min_value=0.5, value=float(delivery["daily_available_hours_default"]), step=0.5)
        buffer_min = d2.number_input("最低バッファ日数", min_value=0, value=int(delivery["buffer_days_min"]))
        buffer_standard = d3.number_input("標準バッファ日数", min_value=0, value=int(delivery["buffer_days_standard"]))

        d4, d5, d6 = st.columns(3)
        revision_buffer = d4.number_input("修正対応バッファ日数", min_value=0, value=int(delivery["revision_buffer_days"]))
        material_buffer = d5.number_input("素材待ちバッファ日数", min_value=0, value=int(delivery["material_wait_buffer_days"]))
        api_buffer = d6.number_input("API審査待ちバッファ日数", min_value=0, value=int(delivery["api_review_buffer_days"]))

        if st.form_submit_button("納期設定を保存する", type="primary"):
            new_delivery = {
                **delivery, "daily_available_hours_default": float(daily_hours), "buffer_days_min": int(buffer_min),
                "buffer_days_standard": int(buffer_standard), "revision_buffer_days": int(revision_buffer),
                "material_wait_buffer_days": int(material_buffer), "api_review_buffer_days": int(api_buffer),
            }
            with session() as conn:
                save_delivery_settings(conn, new_delivery)
            st.success("納期設定を保存しました。")
            st.rerun()

    st.caption(f"対応テンプレートカテゴリ: {'、'.join(TEMPLATE_CATEGORIES)}")
