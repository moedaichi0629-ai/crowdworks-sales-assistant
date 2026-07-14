"""案件追加ページ: URLから取得 / 手動入力 / CSVアップロード の3方式に対応。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.config import DEFAULT_SETTINGS, JOB_TYPES
from src.csv_import import auto_map_columns, import_dataframe, read_csv_bytes
from src.database import init_db, session
from src.job_collector import collect_jobs_from_urls
from src.logger import get_logger
from src.manual_import import extract_preview_from_body, save_manual_job
from src.repositories import get_all_settings
from src.validators import ValidationError

st.set_page_config(page_title="案件追加 | クラウドワークス案件管理ツール", page_icon="➕", layout="wide")
logger = get_logger()
init_db()

st.title("➕ 案件を追加")

tab_url, tab_manual, tab_csv = st.tabs(["URLから取得", "手動入力", "CSVアップロード"])

# ============================= URLから取得 =============================
with tab_url:
    st.markdown(
        "外部サイトの利用規約・robots.txtで自動取得が許可されていることを確認できた"
        "公開ページのみを指定してください。"
    )
    st.warning(
        "**クラウドワークス(crowdworks.jp)について**: robots.txtでAIクローラー(ClaudeBot等)が"
        "明示的にブロックされており、`/api/`も公開API以外は取得禁止のため、本ツールから"
        "crowdworks.jpへ自動アクセスすることはできません。クラウドワークスの案件は"
        "「手動入力」または「CSVアップロード」タブをご利用ください。"
    )

    with session() as conn:
        settings = get_all_settings(conn)

    url_text = st.text_area(
        "取得したい案件詳細ページURL（1行に1件、複数可）",
        height=120,
        placeholder="https://example.com/jobs/12345\nhttps://example.com/jobs/12346",
    )
    keyword_for_urls = st.selectbox(
        "検索キーワード（取得結果に紐付けます）",
        options=[""] + settings.get("search_keywords", DEFAULT_SETTINGS["search_keywords"]),
    )
    max_count = st.number_input(
        "最大取得件数", min_value=1, max_value=100,
        value=int(settings.get("max_fetch_count", 20)),
    )
    wait_seconds = st.number_input(
        "取得時の待機秒数", min_value=1.0, max_value=30.0,
        value=float(settings.get("fetch_wait_seconds", 3.0)), step=0.5,
    )

    if st.button("URLから取得を実行", type="primary"):
        urls = [u.strip() for u in url_text.splitlines() if u.strip()]
        if not urls:
            st.error("取得したいURLを1件以上入力してください。")
        else:
            with st.spinner("取得中です。しばらくお待ちください…"):
                try:
                    with session() as conn:
                        result = collect_jobs_from_urls(
                            conn, urls, keyword=keyword_for_urls,
                            max_count=int(max_count), wait_seconds=float(wait_seconds),
                        )
                    st.success(
                        f"取得完了: 対象{result['total']}件 / 新規{result['inserted']}件 / "
                        f"更新{result['updated']}件 / 重複{result['duplicate']}件 / エラー{result['errors']}件"
                    )
                    if result["error_rows"]:
                        st.error("取得できなかったURLがあります（詳細はlogs/app.logをご確認ください）")
                        st.dataframe(pd.DataFrame(result["error_rows"]), width="stretch", hide_index=True)
                except Exception:
                    logger.exception("URL取得処理で予期しないエラーが発生しました。")
                    st.error("URL取得中に予期しないエラーが発生しました。時間をおいて再度お試しください。")

# ============================= 手動入力 =============================
with tab_manual:
    st.markdown("案件本文を貼り付けると、予算や応募期限などを自動抽出して下部の入力欄に反映します。")

    with session() as conn:
        settings = get_all_settings(conn)

    body_input = st.text_area("案件本文（貼り付けると自動抽出を試みます）", height=150, key="manual_body")

    extracted = {}
    if body_input:
        if st.button("本文から自動抽出する"):
            extracted = extract_preview_from_body(body_input)
            st.session_state["manual_extracted"] = extracted
            st.success("自動抽出しました。下記の入力欄で内容を確認・修正してください。")

    extracted = st.session_state.get("manual_extracted", {})

    with st.form("manual_job_form", clear_on_submit=False):
        title = st.text_input("案件タイトル（必須）")
        url = st.text_input("案件URL")
        col1, col2 = st.columns(2)
        with col1:
            job_type = st.selectbox("募集形式", options=[""] + JOB_TYPES,
                                     index=(JOB_TYPES.index(extracted.get("job_type")) + 1) if extracted.get("job_type") in JOB_TYPES else 0)
            category = st.text_input("カテゴリ")
            budget_text = st.text_input("予算", value=extracted.get("budget_text") or "")
            published_at = st.text_input("掲載日時（例: 2026-07-10）")
            deadline = st.text_input("応募期限（例: 2026-07-20）", value=extracted.get("deadline") or "")
        with col2:
            applicant_count = st.number_input("応募人数", min_value=0, value=int(extracted.get("applicant_count") or 0))
            recruitment_count = st.number_input("採用人数", min_value=0, value=int(extracted.get("recruitment_count") or 0))
            client_name = st.text_input("クライアント名", value=extracted.get("client_name") or "")
            client_rating = st.number_input("クライアント評価", min_value=0.0, max_value=5.0, step=0.1)
            identity_verified = st.checkbox("本人確認済み")

        matched_keyword = st.selectbox(
            "検索キーワード", options=[""] + settings.get("search_keywords", DEFAULT_SETTINGS["search_keywords"])
        )
        memo = st.text_area("メモ")

        submitted = st.form_submit_button("この内容で登録する", type="primary")

        if submitted:
            form_data = {
                "title": title,
                "url": url or None,
                "body": body_input or None,
                "job_type": job_type or None,
                "category": category or None,
                "budget_text": budget_text or None,
                "published_at": published_at or None,
                "deadline": deadline or None,
                "applicant_count": applicant_count or None,
                "recruitment_count": recruitment_count or None,
                "client_name": client_name or None,
                "client_rating": client_rating or None,
                "identity_verified": 1 if identity_verified else None,
                "matched_keyword": matched_keyword or None,
                "memo": memo or None,
            }
            try:
                with session() as conn:
                    action, job_id = save_manual_job(conn, form_data)
                labels = {"inserted": "新規登録", "updated": "更新", "duplicate": "重複（既存案件のまま）"}
                st.success(f"{labels[action]}しました（案件ID: {job_id}）。")
                st.session_state.pop("manual_extracted", None)
            except ValidationError as exc:
                st.error(str(exc))
            except Exception:
                logger.exception("手動入力の保存に失敗しました。")
                st.error("案件の保存に失敗しました。入力内容をご確認のうえ再度お試しください。")

# ============================= CSVアップロード =============================
with tab_csv:
    st.markdown("CSVファイルをアップロードして案件を一括登録できます。")
    with open("data/sample_jobs.csv", "rb") as f:
        st.download_button("サンプルCSVをダウンロード", f, file_name="sample_jobs.csv", mime="text/csv")

    uploaded = st.file_uploader("CSVファイルを選択", type=["csv"])

    if uploaded is not None:
        try:
            file_bytes = uploaded.getvalue()
            df = read_csv_bytes(file_bytes, uploaded.name)
            st.write(f"{len(df)}件のデータを読み込みました。")

            mapping, unmapped = auto_map_columns(list(df.columns))

            if "title" not in mapping:
                st.warning("案件タイトルに該当する列を自動判定できませんでした。手動でマッピングしてください。")

            with st.expander("CSV列マッピングを確認・修正する", expanded=("title" not in mapping)):
                field_labels = {
                    "external_job_id": "外部案件ID", "title": "案件タイトル(必須)", "url": "案件URL",
                    "description": "案件概要", "body": "案件本文", "job_type": "募集形式", "category": "カテゴリ",
                    "budget": "予算", "budget_min": "予算下限", "budget_max": "予算上限",
                    "published_at": "掲載日時", "deadline": "応募期限", "applicant_count": "応募人数",
                    "recruitment_count": "採用人数", "client_name": "クライアント名", "client_rating": "クライアント評価",
                    "identity_verified": "本人確認", "keyword": "検索キーワード", "memo": "メモ",
                }
                new_mapping = {}
                options = ["（対応なし）"] + list(df.columns)
                for field, label in field_labels.items():
                    default_col = mapping.get(field)
                    default_index = options.index(default_col) if default_col in options else 0
                    chosen = st.selectbox(label, options=options, index=default_index, key=f"map_{field}")
                    if chosen != "（対応なし）":
                        new_mapping[field] = chosen
                mapping = new_mapping

            st.subheader("プレビュー（先頭5件）")
            st.dataframe(df.head(5), width="stretch")

            default_keyword = st.selectbox("登録データに付与する検索キーワード（任意）", options=[""] + DEFAULT_SETTINGS["search_keywords"])

            if st.button("この内容で一括登録する", type="primary"):
                if "title" not in mapping:
                    st.error("案件タイトルの列を指定してください。")
                else:
                    with st.spinner("登録処理中です…"):
                        with session() as conn:
                            result = import_dataframe(conn, df, mapping, uploaded.name, default_keyword)
                    st.success(
                        f"登録完了: 全{result['total']}件 / 新規{result['inserted']}件 / "
                        f"更新{result['updated']}件 / 重複{result['duplicate']}件 / エラー{result['errors']}件"
                    )
                    if result["error_rows"]:
                        st.error("登録できなかった行があります。")
                        st.dataframe(pd.DataFrame(result["error_rows"]), width="stretch", hide_index=True)
        except ValidationError as exc:
            st.error(str(exc))
        except Exception:
            logger.exception("CSVインポート処理で予期しないエラーが発生しました。")
            st.error("CSVの読み込みに失敗しました。ファイル形式・文字コードをご確認のうえ再度お試しください。")
