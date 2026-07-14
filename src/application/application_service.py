"""営業文生成のサービス層。Streamlitページから呼び出す高レベルAPI。"""
from __future__ import annotations

import sqlite3
import time

from src.ai.provider_factory import get_ai_client
from src.application.application_cache import get_cached_draft
from src.application.application_generator import GenerationBlockedError, generate_application
from src.application.version_service import record_version
from src.config import (
    DEFAULT_APPLICATION_MODELS,
    LENGTH_DETAILED,
    LENGTH_SHORT,
    LENGTH_STANDARD,
    PREP_STATUS_COPIED,
    PREP_STATUS_EDITING,
    TONE_ACHIEVEMENT,
    TONE_DESIGN,
    TONE_ENTHUSIASTIC,
    TONE_PROPOSAL,
    TONE_SINCERE_BEGINNER,
    TONE_TECHNICAL,
)
from src.logger import get_logger
from src.repositories import (
    create_application_draft,
    get_all_analysis_settings,
    get_application_draft,
    get_current_application_draft,
    get_job,
    get_latest_analysis,
    get_profile_bundle,
    mark_application_draft_copied,
    update_application_draft,
)

logger = get_logger()

# 「営業文編集機能」の指示ラベル → トーン/長さの上書き値。
# AI再生成時のヒントとしても additional_message へ渡す。
EDIT_INSTRUCTION_MAP: dict[str, dict] = {
    "短くする": {"length_type": LENGTH_SHORT},
    "詳しくする": {"length_type": LENGTH_DETAILED},
    "丁寧にする": {"tone": "丁寧"},
    "熱意を強くする": {"tone": TONE_ENTHUSIASTIC},
    "技術説明を増やす": {"tone": TONE_TECHNICAL},
    "デザイン説明を増やす": {"tone": TONE_DESIGN},
    "実績を強調する": {"tone": TONE_ACHIEVEMENT},
    "提案内容を増やす": {"tone": TONE_PROPOSAL},
    "初心者らしい誠実さを加える": {"tone": TONE_SINCERE_BEGINNER},
    "不自然な表現を修正する": {"hint": "AIが作ったような不自然な表現があれば、自然な日本語に修正してください。"},
    "誤字脱字を修正する": {"hint": "誤字脱字があれば修正してください。"},
}


def _build_application_ai_client(analysis_settings: dict, force_template: bool = False):
    if force_template or analysis_settings.get("rule_based_only"):
        return None
    models = analysis_settings.get("application_ai_models") or DEFAULT_APPLICATION_MODELS
    return get_ai_client(
        analysis_settings.get("ai_provider"),
        models=models,
        timeout_seconds=analysis_settings.get("api_timeout_seconds", 30),
        max_retry_count=analysis_settings.get("max_retry_count", 1),
    )


def generate_for_job(
    conn: sqlite3.Connection,
    job_id: int,
    tone: str | None = None,
    length_type: str = LENGTH_STANDARD,
    show_headings: bool = True,
    additional_message: str | None = None,
    exclude_content: str | None = None,
    manual_portfolio_ids: list[int] | None = None,
    price_override: int | None = None,
    delivery_days_override: int | None = None,
    force_template: bool = False,
    force_regenerate: bool = False,
) -> dict:
    """1案件の営業文を生成・保存する。危険案件の場合は GenerationBlockedError を送出する。"""
    job = get_job(conn, job_id)
    if job is None:
        raise ValueError(f"案件が見つかりません: job_id={job_id}")

    profile_bundle = get_profile_bundle(conn)
    if profile_bundle is None:
        raise ValueError("スキルプロフィールが未登録です。先にプロフィールを作成してください。")

    analysis_settings = get_all_analysis_settings(conn)
    latest_analysis = get_latest_analysis(conn, job_id)
    ai_client = _build_application_ai_client(analysis_settings, force_template=force_template)

    result = generate_application(
        conn, job, profile_bundle, latest_analysis, ai_client,
        generation_type="template" if force_template else "ai",
        tone=tone, length_type=length_type, show_headings=show_headings,
        additional_message=additional_message, exclude_content=exclude_content,
        manual_portfolio_ids=manual_portfolio_ids,
        price_override=price_override, delivery_days_override=delivery_days_override,
        max_tokens=analysis_settings.get("application_max_tokens", 2000),
    )

    existing_draft = get_current_application_draft(conn, job_id)

    if not force_regenerate and existing_draft and existing_draft.get("source_hash") == result["source_hash"]:
        logger.info("営業文のキャッシュを利用しました: job_id=%s", job_id)
        return {
            **existing_draft, "draft_id": existing_draft["id"], "_from_cache": True,
            "full_message": existing_draft.get("application_message"),
        }

    draft_data = {k: v for k, v in result.items() if k not in ("client_questions", "candidate_portfolios", "char_count")}
    draft_data["profile_id"] = profile_bundle["profile"]["id"]
    draft_data["analysis_id"] = latest_analysis.get("id") if latest_analysis else None
    draft_data["application_message"] = draft_data.pop("full_message")

    if existing_draft:
        record_version(
            conn, existing_draft["id"], existing_draft.get("application_message") or "",
            existing_draft.get("short_message"), version_type="pre_regenerate",
            change_instruction="再生成前の状態を保存",
        )
        update_application_draft(conn, existing_draft["id"], draft_data)
        draft_id = existing_draft["id"]
    else:
        draft_id = create_application_draft(conn, job_id, draft_data)

    record_version(
        conn, draft_id, draft_data["application_message"], draft_data.get("short_message"),
        version_type=result.get("generation_type", "generated"),
    )

    result["application_message"] = draft_data["application_message"]
    result["draft_id"] = draft_id
    result["_from_cache"] = False
    return result


def select_application_target_jobs(conn: sqlite3.Connection, target_mode: str, selected_ids: list[int] | None = None) -> list[dict]:
    """営業文の一括生成対象となる案件一覧を取得する。"""
    from src.repositories import get_jobs_with_latest_application

    all_jobs = get_jobs_with_latest_application(conn)

    if target_mode == "未生成案件のみ":
        return [j for j in all_jobs if j.get("draft_id") is None]
    if target_mode == "選択した案件":
        ids = set(selected_ids or [])
        return [j for j in all_jobs if j["id"] in ids]
    if target_mode == "応募候補ステータスのみ":
        from src.config import STATUS_CANDIDATE

        return [j for j in all_jobs if j.get("status") == STATUS_CANDIDATE]
    if target_mode == "応募優先度が高い案件のみ":
        from src.repositories import get_jobs_with_latest_analysis

        priority_jobs = {j["id"]: j.get("application_priority") for j in get_jobs_with_latest_analysis(conn)}
        return [j for j in all_jobs if priority_jobs.get(j["id"]) in ("最優先", "優先")]
    if target_mode == "全案件を再生成":
        return all_jobs
    return all_jobs


def run_bulk_generation(
    conn: sqlite3.Connection,
    job_ids: list[int],
    wait_seconds: float = 2.0,
    max_count: int = 5,
    tone: str | None = None,
    length_type: str = LENGTH_STANDARD,
    force_template: bool = False,
    progress_callback=None,
) -> dict:
    """複数案件の営業文をまとめて生成する。危険案件はスキップして処理を継続する。"""
    target_ids = job_ids[:max_count]
    success = failed = blocked = 0

    for i, job_id in enumerate(target_ids):
        try:
            generate_for_job(
                conn, job_id, tone=tone, length_type=length_type,
                force_template=force_template, force_regenerate=False,
            )
            success += 1
        except GenerationBlockedError:
            blocked += 1
        except Exception:
            logger.exception("営業文の一括生成中にエラーが発生しました: job_id=%s", job_id)
            failed += 1

        if progress_callback:
            progress_callback(i + 1, len(target_ids))
        if i < len(target_ids) - 1:
            time.sleep(wait_seconds)

    logger.info(
        "営業文の一括生成が完了しました: total=%s success=%s failed=%s blocked=%s",
        len(target_ids), success, failed, blocked,
    )
    return {"total": len(target_ids), "success": success, "failed": failed, "blocked": blocked}


def manual_edit_application(
    conn: sqlite3.Connection, draft_id: int, application_message: str, short_message: str | None = None,
) -> None:
    """ユーザーによる直接編集を保存する（再生成では上書きされない）。"""
    update_application_draft(conn, draft_id, {
        "application_message": application_message,
        "short_message": short_message,
        "preparation_status": PREP_STATUS_EDITING,
    })
    record_version(conn, draft_id, application_message, short_message, version_type="manual_edit", created_by="user")
    logger.info("営業文を手動編集しました: draft_id=%s", draft_id)


def edit_with_instruction(
    conn: sqlite3.Connection, job_id: int, instruction_label: str, force_template: bool = False,
) -> dict:
    """営業文編集機能の定型指示（短くする・丁寧にする 等）を適用して再生成する。"""
    draft = get_current_application_draft(conn, job_id)
    overrides = EDIT_INSTRUCTION_MAP.get(instruction_label, {})

    tone = overrides.get("tone") or (draft.get("tone") if draft else None)
    length_type = overrides.get("length_type") or (draft.get("length_type") if draft else LENGTH_STANDARD)
    additional_message = overrides.get("hint")

    return generate_for_job(
        conn, job_id, tone=tone, length_type=length_type, additional_message=additional_message,
        force_template=force_template, force_regenerate=True,
    )


def copy_application(conn: sqlite3.Connection, draft_id: int) -> None:
    """営業文をコピーした事実を記録する（コピーしただけでは「応募済み」にはしない）。"""
    mark_application_draft_copied(conn, draft_id)


def get_draft_detail(conn: sqlite3.Connection, draft_id: int) -> dict | None:
    return get_application_draft(conn, draft_id)
