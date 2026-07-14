"""スキルプロフィール管理ページ: 基本情報・スキル・制作実績・希望条件などを編集する。"""
from __future__ import annotations

import streamlit as st

from src.config import EXPERIENCE_TYPES, PROFICIENCY_LEVELS, SKILL_CATEGORIES
from src.database import init_db, session
from src.logger import get_logger
from src.profile.profile_service import (
    add_profile_portfolio,
    add_profile_skill,
    edit_profile_portfolio,
    edit_profile_skill,
    get_full_profile,
    remove_profile_portfolio,
    remove_profile_skill,
    save_basic_info,
)

st.set_page_config(page_title="スキルプロフィール | クラウドワークス案件管理ツール", page_icon="🧑‍💻", layout="wide")
logger = get_logger()
init_db()

st.title("🧑‍💻 スキルプロフィール")
st.caption("ここで登録した内容がAI案件分析（適合度判定）の基礎情報として使用されます。")

with session() as conn:
    bundle = get_full_profile(conn)

profile = bundle["profile"]
skills = bundle["skills"]
portfolios = bundle["portfolios"]

tab_basic, tab_conditions, tab_skills, tab_portfolios = st.tabs(
    ["基本情報", "希望条件・対応が難しい業務", "スキル", "制作実績"]
)

# ============================= 基本情報 =============================
with tab_basic:
    basic_info = profile.get("basic_info") or {}
    with st.form("basic_info_form"):
        display_name = st.text_input("表示名", value=profile.get("display_name") or "")
        job_title = st.text_input("職種", value=profile.get("job_title") or "")
        experience_level = st.text_area("経験段階", value=profile.get("experience_level") or "")
        daily_hours = st.text_input("1日あたりの作業時間目安", value=profile.get("daily_available_hours") or "")
        languages = st.text_input("対応言語（カンマ区切り）", value="、".join(basic_info.get("languages", [])))
        desired_jobs = st.text_input("希望する案件", value=basic_info.get("desired_jobs") or "")
        contact_availability = st.text_input("連絡可能時間", value=basic_info.get("contact_availability") or "")
        response_policy = st.text_area("対応方針", value=basic_info.get("response_policy") or "")

        if st.form_submit_button("基本情報を保存する", type="primary"):
            data = {
                "display_name": display_name,
                "job_title": job_title,
                "experience_level": experience_level,
                "daily_available_hours": daily_hours,
                "basic_info": {
                    "languages": [s.strip() for s in languages.split("、") if s.strip()] or [s.strip() for s in languages.split(",") if s.strip()],
                    "desired_jobs": desired_jobs,
                    "contact_availability": contact_availability,
                    "response_policy": response_policy,
                },
            }
            with session() as conn:
                save_basic_info(conn, profile["id"], data)
            st.success("基本情報を保存しました。")
            st.rerun()

# ============================= 希望条件・対応が難しい業務 =============================
with tab_conditions:
    preferred = profile.get("preferred_conditions") or {}
    difficult = profile.get("difficult_conditions") or {}

    def _editable_list(section_title: str, items: list[str], key_prefix: str, save_fn):
        st.markdown(f"#### {section_title}")
        items = list(items)
        new_item = st.text_input(f"{section_title}を追加", key=f"new_{key_prefix}")
        if st.button("追加する", key=f"add_{key_prefix}"):
            if new_item and new_item not in items:
                items.append(new_item)
                save_fn(items)
                st.rerun()
        for item in items:
            c1, c2 = st.columns([5, 1])
            c1.write(item)
            if c2.button("削除", key=f"del_{key_prefix}_{item}"):
                items.remove(item)
                save_fn(items)
                st.rerun()

    def _save_preferred(field: str):
        def _fn(items: list[str]):
            new_preferred = dict(preferred)
            new_preferred[field] = items
            with session() as conn:
                save_basic_info(conn, profile["id"], {"preferred_conditions": new_preferred})
        return _fn

    def _save_difficult(field: str):
        def _fn(items: list[str]):
            new_difficult = dict(difficult)
            new_difficult[field] = items
            with session() as conn:
                save_basic_info(conn, profile["id"], {"difficult_conditions": new_difficult})
        return _fn

    col1, col2 = st.columns(2)
    with col1:
        _editable_list("希望条件", preferred.get("preferred_conditions", []), "pref_cond", _save_preferred("preferred_conditions"))
        st.divider()
        _editable_list("対応可能な業務", preferred.get("attainable_tasks", []), "attain_task", _save_preferred("attainable_tasks"))
    with col2:
        _editable_list("対応が難しい業務", difficult.get("difficult_conditions", []), "diff_cond", _save_difficult("difficult_conditions"))
        st.divider()
        _editable_list("除外条件", difficult.get("excluded_conditions", []), "excl_cond", _save_difficult("excluded_conditions"))

# ============================= スキル =============================
with tab_skills:
    st.markdown("#### スキル一覧")
    category_filter = st.selectbox("カテゴリで絞り込み", options=["すべて"] + SKILL_CATEGORIES)
    display_skills = skills if category_filter == "すべて" else [s for s in skills if s["category"] == category_filter]

    for s in display_skills:
        with st.expander(f"[{s['category']}] {s['skill_name']}（{s.get('proficiency_level') or '-'}）"):
            with st.form(f"skill_form_{s['id']}"):
                c1, c2, c3 = st.columns(3)
                name = c1.text_input("スキル名", value=s["skill_name"], key=f"skill_name_{s['id']}")
                proficiency = c2.selectbox(
                    "習熟度", options=PROFICIENCY_LEVELS,
                    index=PROFICIENCY_LEVELS.index(s["proficiency_level"]) if s.get("proficiency_level") in PROFICIENCY_LEVELS else 0,
                    key=f"prof_{s['id']}",
                )
                exp_type = c3.selectbox(
                    "経験区分", options=EXPERIENCE_TYPES,
                    index=EXPERIENCE_TYPES.index(s["experience_type"]) if s.get("experience_type") in EXPERIENCE_TYPES else 0,
                    key=f"exp_{s['id']}",
                )
                memo = st.text_input("メモ", value=s.get("memo") or "", key=f"memo_{s['id']}")

                save_col, del_col = st.columns(2)
                if save_col.form_submit_button("保存"):
                    with session() as conn:
                        edit_profile_skill(conn, s["id"], {
                            "skill_name": name, "proficiency_level": proficiency,
                            "experience_type": exp_type, "memo": memo,
                        })
                    st.success("保存しました。")
                    st.rerun()
                if del_col.form_submit_button("削除"):
                    with session() as conn:
                        remove_profile_skill(conn, s["id"])
                    st.success("削除しました。")
                    st.rerun()

    st.divider()
    st.markdown("#### 新しいスキルを追加")
    with st.form("add_skill_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        new_category = c1.selectbox("カテゴリ", options=SKILL_CATEGORIES, index=1)
        new_name = c2.text_input("スキル名")
        new_proficiency = c3.selectbox("習熟度", options=PROFICIENCY_LEVELS)
        new_exp_type = st.selectbox("経験区分", options=EXPERIENCE_TYPES)
        if st.form_submit_button("追加する", type="primary"):
            if new_name:
                with session() as conn:
                    add_profile_skill(conn, profile["id"], {
                        "category": new_category, "skill_name": new_name,
                        "proficiency_level": new_proficiency, "experience_type": new_exp_type,
                    })
                st.success("スキルを追加しました。")
                st.rerun()
            else:
                st.warning("スキル名を入力してください。")

# ============================= 制作実績 =============================
with tab_portfolios:
    st.markdown("#### 制作実績一覧")
    for p in portfolios:
        with st.expander(p["title"]):
            with st.form(f"portfolio_form_{p['id']}"):
                title = st.text_input("タイトル", value=p["title"], key=f"pf_title_{p['id']}")
                description = st.text_area("説明", value=p.get("description") or "", key=f"pf_desc_{p['id']}")
                technologies = st.text_input("使用技術（カンマ区切り）", value=", ".join(p.get("technologies", [])), key=f"pf_tech_{p['id']}")
                skills_text = st.text_input("関連スキル（カンマ区切り）", value=", ".join(p.get("skills", [])), key=f"pf_skills_{p['id']}")
                portfolio_url = st.text_input("ポートフォリオURL", value=p.get("portfolio_url") or "", key=f"pf_url_{p['id']}")
                github_url = st.text_input("GitHub URL", value=p.get("github_url") or "", key=f"pf_gh_{p['id']}")

                save_col, del_col = st.columns(2)
                if save_col.form_submit_button("保存"):
                    with session() as conn:
                        edit_profile_portfolio(conn, p["id"], {
                            "title": title, "description": description,
                            "technologies": [t.strip() for t in technologies.split(",") if t.strip()],
                            "skills": [s.strip() for s in skills_text.split(",") if s.strip()],
                            "portfolio_url": portfolio_url or None, "github_url": github_url or None,
                        })
                    st.success("保存しました。")
                    st.rerun()
                if del_col.form_submit_button("削除"):
                    with session() as conn:
                        remove_profile_portfolio(conn, p["id"])
                    st.success("削除しました。")
                    st.rerun()

    st.divider()
    st.markdown("#### 新しい制作実績を追加")
    with st.form("add_portfolio_form", clear_on_submit=True):
        new_title = st.text_input("タイトル")
        new_description = st.text_area("説明")
        new_technologies = st.text_input("使用技術（カンマ区切り）")
        new_skills = st.text_input("関連スキル（カンマ区切り）")
        new_portfolio_url = st.text_input("ポートフォリオURL")
        new_github_url = st.text_input("GitHub URL")
        if st.form_submit_button("追加する", type="primary"):
            if new_title:
                with session() as conn:
                    add_profile_portfolio(conn, profile["id"], {
                        "title": new_title, "description": new_description,
                        "technologies": [t.strip() for t in new_technologies.split(",") if t.strip()],
                        "skills": [s.strip() for s in new_skills.split(",") if s.strip()],
                        "portfolio_url": new_portfolio_url or None, "github_url": new_github_url or None,
                    })
                st.success("制作実績を追加しました。")
                st.rerun()
            else:
                st.warning("タイトルを入力してください。")
