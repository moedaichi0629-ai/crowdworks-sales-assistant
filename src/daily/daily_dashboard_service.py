"""本日の営業ダッシュボードの集計・候補操作を行うサービス層。"""
from __future__ import annotations

import sqlite3

from src.config import (
    CANDIDATE_STATUS_ACTIVE,
    CANDIDATE_STATUS_APPLIED,
    CANDIDATE_STATUS_EXCLUDED,
    CANDIDATE_STATUS_POSTPONED,
    CANDIDATE_STATUS_REMOVED,
    CANDIDATE_STATUS_SKIPPED,
    CATEGORY_GROUP_AI_DEV,
    CATEGORY_GROUP_DESIGN,
    CATEGORY_GROUP_OTHER,
    PREP_STATUS_NONE,
    PREP_STATUS_READY,
)
from src.daily.candidate_selector import select_daily_candidates
from src.daily.goal_service import ensure_daily_goal
from src.logger import get_logger
from src.repositories import (
    count_applications_for_date,
    get_daily_candidate,
    get_daily_candidates,
    update_daily_candidate,
    upsert_daily_candidate,
)

logger = get_logger()


def get_or_select_candidates(conn: sqlite3.Connection, target_date: str) -> list[dict]:
    """本日の候補一覧を取得する。まだ候補が1件も無い日付の場合は自動選定する（日付変更時の自動作成）。"""
    candidates = get_daily_candidates(conn, target_date)
    if not candidates:
        select_daily_candidates(conn, target_date)
        candidates = get_daily_candidates(conn, target_date)
    return candidates


def reselect_candidates(conn: sqlite3.Connection, target_date: str) -> dict:
    """本日の候補を再選定する（手動追加・保留・見送り・除外・応募済みの行は保持する）。"""
    logger.info("候補再選定: target_date=%s", target_date)
    return select_daily_candidates(conn, target_date)


def build_dashboard(conn: sqlite3.Connection, target_date: str) -> dict:
    """本日の営業ダッシュボードに必要な集計値をまとめて返す。"""
    goal = ensure_daily_goal(conn, target_date)
    candidates = get_or_select_candidates(conn, target_date)
    applied_count = count_applications_for_date(conn, target_date)

    active = [c for c in candidates if c["candidate_status"] == CANDIDATE_STATUS_ACTIVE]
    excluded = [c for c in candidates if c["candidate_status"] == CANDIDATE_STATUS_EXCLUDED]
    postponed = [c for c in candidates if c["candidate_status"] == CANDIDATE_STATUS_POSTPONED]
    skipped = [c for c in candidates if c["candidate_status"] == CANDIDATE_STATUS_SKIPPED]
    removed = [c for c in candidates if c["candidate_status"] == CANDIDATE_STATUS_REMOVED]

    target_count = int(goal.get("target_count", 0) or 0)
    maximum_count = int(goal.get("maximum_count", 0) or 0)

    ready_count = sum(1 for c in active if c.get("preparation_status") == PREP_STATUS_READY)
    no_draft_count = sum(
        1 for c in active if not c.get("preparation_status") or c.get("preparation_status") == PREP_STATUS_NONE
    )

    goal_status = {
        "target_count": target_count,
        "maximum_count": maximum_count,
        "applied_count": applied_count,
        "remaining_to_target": max(0, target_count - applied_count),
        "remaining_to_maximum": max(0, maximum_count - applied_count),
        "achievement_rate": round(applied_count / target_count * 100, 1) if target_count else 0.0,
        "goal_achieved": applied_count >= target_count > 0,
        "limit_reached": maximum_count > 0 and applied_count >= maximum_count,
        "ready_count": ready_count,
        "no_draft_count": no_draft_count,
    }

    candidate_status = {
        "total_candidates": len(active),
        "ai_dev_count": sum(1 for c in active if c["category_group"] == CATEGORY_GROUP_AI_DEV),
        "design_count": sum(1 for c in active if c["category_group"] == CATEGORY_GROUP_DESIGN),
        "other_count": sum(1 for c in active if c["category_group"] == CATEGORY_GROUP_OTHER),
        "top_priority_count": sum(1 for c in active if c["daily_priority_score"] >= 80),
        "safety_caution_count": sum(1 for c in active if c["daily_priority_score"] < 50),
        "deadline_soon_count": sum(
            1 for c in active if c.get("deadline") and str(c["deadline"])[:10] <= target_date
        ),
    }

    return {
        "goal": goal, "candidates": active, "excluded": excluded, "postponed": postponed,
        "skipped": skipped, "removed": removed, "goal_status": goal_status,
        "candidate_status": candidate_status,
    }


# ============================= 候補操作 =============================

def add_manual_candidate(conn: sqlite3.Connection, target_date: str, job_id: int, memo: str | None = None) -> int:
    """本日の候補へ手動で案件を追加する（ジャンル枠・スコア条件を無視して追加できる）。"""
    from src.daily.category_allocator import classify_category_group
    from src.repositories import get_current_application_draft, get_job

    job = get_job(conn, job_id)
    if job is None:
        raise ValueError(f"案件が見つかりません: job_id={job_id}")

    draft = get_current_application_draft(conn, job_id)
    candidate_id = upsert_daily_candidate(conn, target_date, job_id, {
        "application_draft_id": (draft or {}).get("id"),
        "category_group": classify_category_group(job),
        "daily_priority_score": 0,
        "rank_number": None,
        "selection_reasons": ["ユーザーが手動で候補に追加した案件"],
        "exclusion_reasons": [],
        "candidate_status": CANDIDATE_STATUS_ACTIVE,
        "is_manually_added": True,
        "user_memo": memo,
    })
    logger.info("候補手動追加: target_date=%s job_id=%s", target_date, job_id)
    return candidate_id


def remove_candidate(conn: sqlite3.Connection, candidate_id: int) -> None:
    """本日の候補から外す（対象外にする。翌日以降は再選定の対象に戻る）。"""
    update_daily_candidate(conn, candidate_id, {
        "candidate_status": CANDIDATE_STATUS_REMOVED, "is_manually_removed": True,
    })
    logger.info("候補手動除外: candidate_id=%s", candidate_id)


def postpone_candidate(conn: sqlite3.Connection, candidate_id: int, postponed_until: str) -> None:
    """候補を明日以降(postponed_until)へ保留する。"""
    update_daily_candidate(conn, candidate_id, {
        "candidate_status": CANDIDATE_STATUS_POSTPONED, "postponed_until": postponed_until,
    })
    logger.info("候補保留: candidate_id=%s postponed_until=%s", candidate_id, postponed_until)


def skip_candidate(conn: sqlite3.Connection, candidate_id: int) -> None:
    """候補を見送りにする（以降の日付でも同じ案件は自動選定の対象外になる）。"""
    update_daily_candidate(conn, candidate_id, {"candidate_status": CANDIDATE_STATUS_SKIPPED})
    logger.info("候補見送り: candidate_id=%s", candidate_id)


def mark_candidate_applied(conn: sqlite3.Connection, candidate_id: int) -> None:
    update_daily_candidate(conn, candidate_id, {"candidate_status": CANDIDATE_STATUS_APPLIED})


def save_candidate_memo(conn: sqlite3.Connection, candidate_id: int, memo: str) -> None:
    update_daily_candidate(conn, candidate_id, {"user_memo": memo})


def get_candidate_detail(conn: sqlite3.Connection, candidate_id: int) -> dict | None:
    return get_daily_candidate(conn, candidate_id)


def get_applied_category_breakdown(conn: sqlite3.Connection, target_date: str) -> dict:
    """指定日に「応募済み」となった候補のジャンル別件数を返す（日別実績画面で使用）。"""
    candidates = get_daily_candidates(conn, target_date)
    applied = [c for c in candidates if c["candidate_status"] == CANDIDATE_STATUS_APPLIED]
    return {
        CATEGORY_GROUP_AI_DEV: sum(1 for c in applied if c["category_group"] == CATEGORY_GROUP_AI_DEV),
        CATEGORY_GROUP_DESIGN: sum(1 for c in applied if c["category_group"] == CATEGORY_GROUP_DESIGN),
        CATEGORY_GROUP_OTHER: sum(1 for c in applied if c["category_group"] == CATEGORY_GROUP_OTHER),
    }
