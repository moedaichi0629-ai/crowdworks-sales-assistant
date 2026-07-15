"""本日の応募候補を自動選定する。

総合スコア・安全度・危険案件除外・応募済み/見送り案件の除外・ジャンル別配分（AI・開発／デザイン／その他）
・不足枠の他ジャンルからの補充（ただし安全度・最低スコア条件を満たした案件のみ）を行う。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime

from src.application.application_validator import check_stop_conditions
from src.config import (
    APPLICATION_MIN_BODY_CHARS,
    CANDIDATE_STATUS_ACTIVE,
    CANDIDATE_STATUS_EXCLUDED,
    CANDIDATE_STATUS_SKIPPED,
    DAILY_EXCLUDED_JOB_STATUSES,
)
from src.daily.category_allocator import allocation_targets, classify_category_group
from src.daily.daily_score_calculator import compute_daily_priority_score
from src.daily.goal_service import ensure_daily_goal
from src.logger import get_logger
from src.portfolio.portfolio_matcher import select_portfolios
from src.repositories import (
    delete_stale_daily_candidates,
    get_active_postponement,
    get_current_application_draft,
    get_daily_candidate_by_job,
    get_jobs_with_latest_analysis,
    get_profile_bundle,
    upsert_daily_candidate,
)

logger = get_logger()


def _days_left(deadline: str | None, target_date: str) -> int | None:
    if not deadline:
        return None
    try:
        d = datetime.strptime(deadline[:10], "%Y-%m-%d").date()
        t = datetime.strptime(target_date, "%Y-%m-%d").date()
        return (d - t).days
    except ValueError:
        return None


def _has_been_skipped(conn: sqlite3.Connection, job_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM daily_candidates WHERE job_id = ? AND candidate_status = ? LIMIT 1",
        (job_id, CANDIDATE_STATUS_SKIPPED),
    ).fetchone()
    return row is not None


def _portfolio_relevance_for_job(job: dict, portfolios: list[dict]) -> tuple[int, list[int]]:
    matches = select_portfolios(job, portfolios)
    selected = [m for m in matches if m["is_selected"]]
    top_score = max((m["relevance_score"] for m in matches), default=0)
    return top_score, [m["portfolio_id"] for m in selected]


def _passes_hard_filters(
    conn: sqlite3.Connection, job: dict, analysis: dict | None, goal: dict, target_date: str, profile: dict | None,
) -> tuple[bool, list[str]]:
    """本日の候補プールに残せるかどうか（安全性・応募条件）を判定する。"""
    reasons: list[str] = []

    if job.get("status") in DAILY_EXCLUDED_JOB_STATUSES:
        reasons.append(f"案件ステータスが「{job.get('status')}」のため対象外")

    days_left = _days_left(job.get("deadline"), target_date)
    if days_left is not None and days_left < 0:
        reasons.append("応募期限を過ぎている")

    existing_today = get_daily_candidate_by_job(conn, target_date, job["id"])
    if existing_today and existing_today.get("is_manually_removed"):
        reasons.append("本日の候補から手動で除外されている")

    postponed_until = get_active_postponement(conn, job["id"], target_date)
    if postponed_until:
        reasons.append(f"{postponed_until}まで保留されている")

    if _has_been_skipped(conn, job["id"]):
        reasons.append("過去に見送りに設定されている")

    body = (job.get("body") or job.get("description") or "").strip()
    if len(body) < APPLICATION_MIN_BODY_CHARS:
        reasons.append("案件本文の情報がほぼ無い")

    if analysis:
        risk_level = analysis.get("risk_level")
        safety_score = analysis.get("safety_score")
        total_score = analysis.get("total_score")
        ai_score = analysis.get("ai_suitability_score")
        allowed_risk_levels = goal.get("allowed_risk_levels") or ["low", "medium"]

        if risk_level == "critical":
            reasons.append("危険レベルが非常に高い")
        elif risk_level and risk_level not in allowed_risk_levels:
            reasons.append(f"危険レベル「{risk_level}」が許可範囲外")

        if safety_score is not None and safety_score < goal.get("minimum_safety_score", 0):
            reasons.append(f"安全度スコア（{safety_score}点）が基準未満")

        if total_score is not None and total_score < goal.get("minimum_total_score", 0):
            reasons.append(f"総合スコア（{total_score}点）が基準未満")

        if ai_score is not None and ai_score < goal.get("minimum_ai_score", 0):
            reasons.append(f"AI適合度（{ai_score}点）が基準未満")

    stop_check = check_stop_conditions(job, analysis, profile)
    if stop_check["should_stop"]:
        reasons.append("営業文生成の停止条件に該当する（危険・低品質の可能性）")

    max_applicants = goal.get("maximum_applicant_count") or 0
    applicant_count = job.get("applicant_count")
    if max_applicants and applicant_count is not None and applicant_count > max_applicants:
        reasons.append(f"応募人数（{applicant_count}人）が上限（{max_applicants}人）を超えている")

    min_rating = goal.get("minimum_client_rating") or 0
    client_rating = job.get("client_rating")
    if min_rating and client_rating is not None and client_rating < min_rating:
        reasons.append(f"クライアント評価（{client_rating}）が基準未満")

    return (len(reasons) == 0, reasons)


def select_daily_candidates(conn: sqlite3.Connection, target_date: str) -> dict:
    """本日（target_date）の応募候補を自動選定し、daily_candidatesへ保存する。

    ユーザーが手動で追加・除外・保留・見送り・応募済みにした行は変更しない。
    戻り値: {"selected_count", "leftover_count", "excluded_count", "goal"}
    """
    logger.info("本日の候補選定開始: target_date=%s", target_date)
    goal = ensure_daily_goal(conn, target_date)
    bundle = get_profile_bundle(conn)
    profile = bundle["profile"] if bundle else None
    portfolios = bundle["portfolios"] if bundle else []

    jobs = get_jobs_with_latest_analysis(conn)
    delete_stale_daily_candidates(conn, target_date)

    pool: list[dict] = []
    excluded_summary = 0

    for job in jobs:
        analysis = job if job.get("analysis_id") else None
        passes, _reasons = _passes_hard_filters(conn, job, analysis, goal, target_date, profile)
        if not passes:
            excluded_summary += 1
            continue

        draft = get_current_application_draft(conn, job["id"])
        portfolio_score, _selected_portfolio_ids = _portfolio_relevance_for_job(job, portfolios)
        category_group = classify_category_group(job)
        weights = goal.get("score_weights") or None
        result = compute_daily_priority_score(job, analysis, portfolio_score, draft, weights)

        pool.append({
            "job": job, "draft": draft, "category_group": category_group,
            "score": result["score"], "reasons": result["reasons"],
        })

    pool.sort(key=lambda x: x["score"], reverse=True)

    targets = allocation_targets(goal)
    selected: list[dict] = []
    selected_ids: set[int] = set()

    for group, quota in targets.items():
        group_pool = [item for item in pool if item["category_group"] == group and item["job"]["id"] not in selected_ids]
        for item in group_pool[:quota]:
            selected.append(item)
            selected_ids.add(item["job"]["id"])

    total_target = int(goal.get("target_count", 0) or 0)
    if len(selected) < total_target:
        remaining_pool = [item for item in pool if item["job"]["id"] not in selected_ids]
        shortage = total_target - len(selected)
        for item in remaining_pool[:shortage]:
            selected.append(item)
            selected_ids.add(item["job"]["id"])

    selected.sort(key=lambda x: x["score"], reverse=True)

    for rank, item in enumerate(selected, start=1):
        upsert_daily_candidate(conn, target_date, item["job"]["id"], {
            "application_draft_id": (item["draft"] or {}).get("id"),
            "category_group": item["category_group"],
            "daily_priority_score": item["score"],
            "rank_number": rank,
            "selection_reasons": item["reasons"],
            "exclusion_reasons": [],
            "candidate_status": CANDIDATE_STATUS_ACTIVE,
        })

    leftover = [item for item in pool if item["job"]["id"] not in selected_ids]
    for item in leftover:
        quota_reason = f"「{item['category_group']}」の本日枠が埋まっている、または本日の目標件数を超えている"
        upsert_daily_candidate(conn, target_date, item["job"]["id"], {
            "application_draft_id": (item["draft"] or {}).get("id"),
            "category_group": item["category_group"],
            "daily_priority_score": item["score"],
            "rank_number": None,
            "selection_reasons": item["reasons"],
            "exclusion_reasons": [quota_reason],
            "candidate_status": CANDIDATE_STATUS_EXCLUDED,
        })

    logger.info(
        "本日の候補選定完了: target_date=%s 選定件数=%s 対象外件数=%s 条件未達除外件数=%s",
        target_date, len(selected), len(leftover), excluded_summary,
    )

    return {
        "selected_count": len(selected), "leftover_count": len(leftover),
        "excluded_count": excluded_summary, "goal": goal,
    }
