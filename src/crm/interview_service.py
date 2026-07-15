"""面談の作成・更新・完了・キャンセル管理。Googleカレンダーへの自動登録は行わない。"""
from __future__ import annotations

import sqlite3

from src.config import (
    APP_STATUS_INTERVIEW_DONE,
    APP_STATUS_INTERVIEW_SCHEDULED,
    APP_STATUS_INTERVIEW_SCHEDULING,
    INTERVIEW_STATUS_CANCELLED,
    INTERVIEW_STATUS_CONFIRMED,
    INTERVIEW_STATUS_DONE,
    INTERVIEW_STATUS_NO_SHOW,
    INTERVIEW_STATUS_SCHEDULING,
)
from src.crm.application_history_service import change_application_status
from src.crm.timeline_service import add_event
from src.logger import get_logger
from src.repositories import (
    create_interview as _create_interview,
    get_interview,
    list_interviews,
    list_interviews_with_job,
    update_interview as _update_interview,
)

logger = get_logger()


def create_interview(
    conn: sqlite3.Connection,
    application_record_id: int,
    title: str | None = None,
    scheduled_start: str | None = None,
    scheduled_end: str | None = None,
    timezone: str = "Asia/Tokyo",
    meeting_type: str | None = None,
    meeting_url: str | None = None,
    contact_name: str | None = None,
    preparation_notes: str | None = None,
    questions: list[str] | None = None,
    self_intro_notes: str | None = None,
    proposal_notes: str | None = None,
) -> int:
    interview_id = _create_interview(conn, {
        "application_record_id": application_record_id, "title": title, "scheduled_start": scheduled_start,
        "scheduled_end": scheduled_end, "timezone": timezone, "meeting_type": meeting_type,
        "meeting_url": meeting_url, "contact_name": contact_name, "preparation_notes": preparation_notes,
        "questions": questions or [], "self_intro_notes": self_intro_notes, "proposal_notes": proposal_notes,
        "status": INTERVIEW_STATUS_SCHEDULING,
    })
    add_event(
        conn, application_record_id, "面談作成", event_title=title or "面談を設定しました",
        event_at=scheduled_start, related_table="interviews", related_id=interview_id,
    )
    change_application_status(conn, application_record_id, APP_STATUS_INTERVIEW_SCHEDULING, change_reason="面談を設定")
    logger.info("面談を作成しました: application_record_id=%s interview_id=%s", application_record_id, interview_id)
    return interview_id


def confirm_interview(conn: sqlite3.Connection, interview_id: int) -> None:
    interview = get_interview(conn, interview_id)
    if interview is None:
        raise ValueError(f"面談が見つかりません: interview_id={interview_id}")
    _update_interview(conn, interview_id, {"status": INTERVIEW_STATUS_CONFIRMED})
    add_event(
        conn, interview["application_record_id"], "面談変更", event_title="面談日程が確定しました",
        related_table="interviews", related_id=interview_id,
    )
    change_application_status(
        conn, interview["application_record_id"], APP_STATUS_INTERVIEW_SCHEDULED, change_reason="面談日程確定",
    )
    logger.info("面談を確定しました: interview_id=%s", interview_id)


def reschedule_interview(
    conn: sqlite3.Connection, interview_id: int, scheduled_start: str, scheduled_end: str | None = None,
) -> None:
    interview = get_interview(conn, interview_id)
    if interview is None:
        raise ValueError(f"面談が見つかりません: interview_id={interview_id}")
    _update_interview(conn, interview_id, {
        "scheduled_start": scheduled_start, "scheduled_end": scheduled_end, "status": INTERVIEW_STATUS_SCHEDULING,
    })
    add_event(
        conn, interview["application_record_id"], "面談変更", event_title="面談日程を変更しました",
        event_at=scheduled_start, related_table="interviews", related_id=interview_id,
    )
    logger.info("面談日程を変更しました: interview_id=%s", interview_id)


def complete_interview(
    conn: sqlite3.Connection, interview_id: int, result: str | None = None, next_step: str | None = None,
    next_contact_due_at: str | None = None, interview_notes: str | None = None,
) -> None:
    interview = get_interview(conn, interview_id)
    if interview is None:
        raise ValueError(f"面談が見つかりません: interview_id={interview_id}")
    _update_interview(conn, interview_id, {
        "status": INTERVIEW_STATUS_DONE, "result": result, "next_step": next_step,
        "next_contact_due_at": next_contact_due_at, "interview_notes": interview_notes,
    })
    add_event(
        conn, interview["application_record_id"], "面談完了", event_title="面談が完了しました",
        event_detail=result, related_table="interviews", related_id=interview_id,
    )
    change_application_status(conn, interview["application_record_id"], APP_STATUS_INTERVIEW_DONE, change_reason="面談完了")
    logger.info("面談を完了として記録しました: interview_id=%s", interview_id)


def cancel_interview(conn: sqlite3.Connection, interview_id: int, no_show: bool = False) -> None:
    interview = get_interview(conn, interview_id)
    if interview is None:
        raise ValueError(f"面談が見つかりません: interview_id={interview_id}")
    status = INTERVIEW_STATUS_NO_SHOW if no_show else INTERVIEW_STATUS_CANCELLED
    _update_interview(conn, interview_id, {"status": status})
    add_event(
        conn, interview["application_record_id"], "面談変更", event_title=f"面談が{status}になりました",
        related_table="interviews", related_id=interview_id,
    )
    logger.info("面談をキャンセルしました: interview_id=%s no_show=%s", interview_id, no_show)


def get_interviews_for_record(conn: sqlite3.Connection, application_record_id: int) -> list[dict]:
    return list_interviews(conn, application_record_id)


def list_all_interviews(conn: sqlite3.Connection) -> list[dict]:
    return list_interviews_with_job(conn)
