"""AI案件分析のサービス層。Streamlitページから呼び出す高レベルAPI。"""
from __future__ import annotations

import sqlite3
import time

from src.ai.provider_factory import get_ai_client
from src.analysis.job_analyzer import analyze_job
from src.config import ANALYSIS_STATUS_UNANALYZED, STATUS_CANDIDATE
from src.logger import get_logger
from src.repositories import (
    get_all_analysis_settings,
    get_all_settings,
    get_job,
    get_profile_bundle,
    save_job_analysis,
)

logger = get_logger()


def _build_ai_client(analysis_settings: dict, rule_only_override: bool = False):
    if rule_only_override or analysis_settings.get("rule_based_only"):
        return None
    return get_ai_client(
        analysis_settings.get("ai_provider"),
        models=analysis_settings.get("ai_models"),
        timeout_seconds=analysis_settings.get("api_timeout_seconds", 30),
        max_retry_count=analysis_settings.get("max_retry_count", 1),
    )


def analyze_single_job(conn: sqlite3.Connection, job_id: int, force_reanalyze: bool = False, rule_only: bool = False) -> dict:
    """1件の案件を分析し、結果をDBへ保存する。"""
    job = get_job(conn, job_id)
    if job is None:
        raise ValueError(f"案件が見つかりません: job_id={job_id}")

    analysis_settings = get_all_analysis_settings(conn)
    profile_bundle = get_profile_bundle(conn)
    if profile_bundle is None:
        raise ValueError("スキルプロフィールが未登録です。先にプロフィールを作成してください。")

    exclude_keywords = get_all_settings(conn).get("exclude_keywords", [])
    ai_client = _build_ai_client(analysis_settings, rule_only_override=rule_only)

    result = analyze_job(
        conn, job, profile_bundle, analysis_settings, ai_client,
        exclude_keywords=exclude_keywords, force_reanalyze=force_reanalyze, rule_only=rule_only,
    )

    if not result.get("_from_cache"):
        save_job_analysis(conn, job_id, result)

    return result


def select_target_jobs(conn: sqlite3.Connection, target_mode: str, selected_ids: list[int] | None = None) -> list[dict]:
    """分析対象の案件一覧を取得する。"""
    from src.repositories import get_jobs_with_latest_analysis
    from src.utils import now_jst_str

    all_jobs = get_jobs_with_latest_analysis(conn)

    if target_mode == "未分析案件のみ":
        return [j for j in all_jobs if j.get("analysis_id") is None]
    if target_mode == "選択した案件":
        ids = set(selected_ids or [])
        return [j for j in all_jobs if j["id"] in ids]
    if target_mode == "応募候補ステータスのみ":
        return [j for j in all_jobs if j.get("status") == STATUS_CANDIDATE]
    if target_mode == "本日取得した案件":
        today = now_jst_str()[:10]
        return [j for j in all_jobs if (j.get("collected_at") or "")[:10] == today]
    if target_mode == "全案件を再分析":
        return all_jobs
    # 条件に合う案件（最低予算・最大応募人数など）は呼び出し側でフィルタ済みのリストを渡す想定
    return all_jobs


def run_bulk_analysis(
    conn: sqlite3.Connection,
    job_ids: list[int],
    wait_seconds: float = 2.0,
    max_count: int = 10,
    force_reanalyze: bool = False,
    rule_only: bool = False,
    progress_callback=None,
) -> dict:
    """複数案件を順番に分析する。APIへの連続送信を避けるため、案件間に待機時間を入れる。"""
    target_ids = job_ids[:max_count]

    success = failed = skipped = api_used = rule_only_count = cache_used = 0

    analysis_settings = get_all_analysis_settings(conn)
    profile_bundle = get_profile_bundle(conn)
    exclude_keywords = get_all_settings(conn).get("exclude_keywords", [])
    ai_client = _build_ai_client(analysis_settings, rule_only_override=rule_only)

    if profile_bundle is None:
        return {
            "total": len(target_ids), "success": 0, "failed": len(target_ids), "skipped": 0,
            "api_used": 0, "rule_only": 0, "cache_used": 0,
            "error": "スキルプロフィールが未登録です。",
        }

    for i, job_id in enumerate(target_ids):
        job = get_job(conn, job_id)
        if job is None:
            skipped += 1
            continue
        result = None
        try:
            result = analyze_job(
                conn, job, profile_bundle, analysis_settings, ai_client,
                exclude_keywords=exclude_keywords, force_reanalyze=force_reanalyze, rule_only=rule_only,
            )
            if result.get("_from_cache"):
                cache_used += 1
            else:
                save_job_analysis(conn, job_id, result)
                if result.get("used_ai"):
                    api_used += 1
                else:
                    rule_only_count += 1
            success += 1
        except Exception:
            logger.exception("一括分析中にエラーが発生しました: job_id=%s", job_id)
            failed += 1

        if progress_callback:
            progress_callback(i + 1, len(target_ids))

        if i < len(target_ids) - 1 and not (result and result.get("_from_cache", False)):
            time.sleep(wait_seconds)

    logger.info(
        "一括分析が完了しました: total=%s success=%s failed=%s skipped=%s api_used=%s rule_only=%s cache_used=%s",
        len(target_ids), success, failed, skipped, api_used, rule_only_count, cache_used,
    )

    return {
        "total": len(target_ids), "success": success, "failed": failed, "skipped": skipped,
        "api_used": api_used, "rule_only": rule_only_count, "cache_used": cache_used,
    }
