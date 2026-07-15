"""正式な応募履歴の記録・応募後ステータス管理を行うサービス層。

「応募済みとして記録」する時点の営業文・分析結果・ポートフォリオはスナップショットとして保存し、
後から元の案件情報・営業文・AI分析結果が変更されても、応募時点の内容がそのまま残るようにする
（要件3・16: スナップショットを後から自動変更しない）。
"""
from __future__ import annotations

import sqlite3

from src.config import (
    APP_STATUS_APPLIED,
    APPLICATION_STATUS_TO_JOB_STATUS,
    CRITICAL_STATUS_CHANGES,
    DEFAULT_SOURCE_PLATFORM,
    PREP_STATUS_APPLIED,
)
from src.crm.timeline_service import add_event
from src.daily.daily_dashboard_service import mark_candidate_applied
from src.logger import get_logger
from src.repositories import (
    add_status_history,
    count_active_application_records_for_job,
    create_application_record,
    deactivate_application_record,
    get_application_draft,
    get_application_record,
    get_current_application_draft,
    get_daily_candidate_by_job,
    get_job,
    get_latest_analysis,
    get_portfolios_by_ids,
    list_application_history as repo_list_application_history,
    list_status_history,
    update_application_draft,
    update_application_record,
    update_status_bulk,
)

logger = get_logger()


class DuplicateApplicationError(Exception):
    """同じ案件へすでに有効な応募記録があり、再応募理由が指定されていない場合に送出する。"""


def _build_snapshot(conn: sqlite3.Connection, job: dict, draft: dict | None) -> dict:
    portfolio_ids = (draft or {}).get("selected_portfolio_ids") or []
    portfolios = get_portfolios_by_ids(conn, portfolio_ids) if portfolio_ids else []
    portfolio_snapshot = [
        {"id": p["id"], "title": p["title"], "portfolio_url": p.get("portfolio_url"), "github_url": p.get("github_url")}
        for p in portfolios
    ]
    portfolio_urls = [u for p in portfolio_snapshot for u in (p.get("portfolio_url"), p.get("github_url")) if u]

    client_snapshot = {
        "client_name": job.get("client_name"), "client_rating": job.get("client_rating"),
        "identity_verified": bool(job.get("identity_verified")),
    }
    job_snapshot = {
        "title": job.get("title"), "url": job.get("url"), "category": job.get("category"),
        "job_type": job.get("job_type"), "budget_min": job.get("budget_min"), "budget_max": job.get("budget_max"),
        "budget_text": job.get("budget_text"), "deadline": job.get("deadline"),
        "published_at": job.get("published_at"), "applicant_count": job.get("applicant_count"),
        "recruitment_count": job.get("recruitment_count"),
    }
    return {
        "portfolio_snapshot": portfolio_snapshot, "portfolio_urls": portfolio_urls,
        "client_snapshot": client_snapshot, "job_snapshot": job_snapshot,
    }


def create_application_history(
    conn: sqlite3.Connection,
    job_id: int,
    application_draft_id: int | None = None,
    target_date: str | None = None,
    source_platform: str = DEFAULT_SOURCE_PLATFORM,
    contract_type: str | None = None,
    tax_type: str | None = None,
    proposed_price: int | None = None,
    proposed_delivery_days: int | None = None,
    proposed_delivery_date: str | None = None,
    user_memo: str | None = None,
    is_over_limit: bool = False,
    over_limit_reason: str | None = None,
    is_reapplication: bool = False,
    reapplication_reason: str | None = None,
) -> int:
    """応募を正式に記録する。

    応募時点の営業文・分析結果・ポートフォリオ・クライアント情報をスナップショットとして保存し、
    案件ステータスを「応募済み」に、営業文の応募準備ステータスを「応募済み」に同期する（要件15）。
    同じ案件にすでに有効な応募記録がある場合は、is_reapplication=True かつ理由が無いと
    DuplicateApplicationError を送出する（要件16: 重複応募の警告・意図的な再応募は理由を保存）。
    """
    existing_active = count_active_application_records_for_job(conn, job_id)
    if existing_active > 0:
        if not is_reapplication or not (reapplication_reason or "").strip():
            logger.warning("重複応募警告: job_id=%s は既に%d件の有効な応募記録があります", job_id, existing_active)
            raise DuplicateApplicationError(
                "この案件にはすでに有効な応募記録があります。意図的な再応募の場合は理由を入力してください。"
            )
        logger.info("意図的な再応募として記録します: job_id=%s（理由の入力あり）", job_id)

    job = get_job(conn, job_id)
    if job is None:
        raise ValueError(f"案件が見つかりません: job_id={job_id}")

    draft = get_application_draft(conn, application_draft_id) if application_draft_id else get_current_application_draft(conn, job_id)
    analysis = get_latest_analysis(conn, job_id)
    candidate = get_daily_candidate_by_job(conn, target_date, job_id) if target_date else None
    snapshot = _build_snapshot(conn, job, draft)

    data = {
        "job_id": job_id,
        "application_draft_id": (draft or {}).get("id"),
        "source_platform": source_platform,
        "contract_type": contract_type,
        "tax_type": tax_type,
        "proposed_price": proposed_price if proposed_price is not None else (draft or {}).get("proposed_price"),
        "proposed_delivery_days": (
            proposed_delivery_days if proposed_delivery_days is not None else (draft or {}).get("proposed_delivery_days")
        ),
        "proposed_delivery_date": proposed_delivery_date,
        "sent_message": (draft or {}).get("application_message"),
        "sent_short_message": (draft or {}).get("short_message"),
        "generation_type": (draft or {}).get("generation_type"),
        "tone": (draft or {}).get("tone"),
        "total_score_snapshot": (analysis or {}).get("total_score"),
        "ai_score_snapshot": (analysis or {}).get("ai_suitability_score"),
        "safety_score_snapshot": (analysis or {}).get("safety_score"),
        "daily_priority_score_snapshot": (candidate or {}).get("daily_priority_score"),
        "applicant_count_snapshot": job.get("applicant_count"),
        "application_status": APP_STATUS_APPLIED,
        "user_memo": user_memo,
        "is_over_limit": is_over_limit,
        "over_limit_reason": over_limit_reason if is_over_limit else None,
        "is_reapplication": is_reapplication,
        "reapplication_reason": reapplication_reason if is_reapplication else None,
        **snapshot,
    }
    record_id = create_application_record(conn, data)

    add_status_history(conn, record_id, None, APP_STATUS_APPLIED, change_reason="正式応募記録の作成")
    add_event(conn, record_id, "応募", event_title="応募しました", event_detail=f"応募経路: {source_platform}")

    update_status_bulk(conn, [job_id], "応募済み")
    if draft:
        update_application_draft(conn, draft["id"], {"preparation_status": PREP_STATUS_APPLIED})
    if candidate:
        mark_candidate_applied(conn, candidate["id"])

    logger.info("正式応募記録を作成しました: job_id=%s record_id=%s 再応募=%s", job_id, record_id, is_reapplication)
    return record_id


def change_application_status(
    conn: sqlite3.Connection, record_id: int, new_status: str,
    change_reason: str | None = None, memo: str | None = None,
) -> dict:
    """応募後ステータスを変更し、履歴・タイムラインを記録し、関連する案件ステータスを同期する。

    採用・不採用・辞退・契約済みなど重要な変更かどうかを返すので、
    呼び出し側（画面）はそれをもとに確認ダイアログを表示すること（要件15）。
    """
    record = get_application_record(conn, record_id)
    if record is None:
        raise ValueError(f"応募履歴が見つかりません: record_id={record_id}")

    previous_status = record.get("application_status")
    update_application_record(conn, record_id, {"application_status": new_status})
    add_status_history(conn, record_id, previous_status, new_status, change_reason=change_reason, memo=memo)
    add_event(
        conn, record_id, "ステータス変更", event_title=f"{previous_status} → {new_status}",
        event_detail=change_reason,
    )

    job_status = APPLICATION_STATUS_TO_JOB_STATUS.get(new_status)
    if job_status:
        update_status_bulk(conn, [record["job_id"]], job_status)

    logger.info("応募後ステータスを変更しました: record_id=%s %s→%s", record_id, previous_status, new_status)
    return {
        "previous_status": previous_status, "new_status": new_status,
        "requires_confirmation": new_status in CRITICAL_STATUS_CHANGES,
    }


def withdraw_application_record(conn: sqlite3.Connection, record_id: int) -> None:
    """応募記録を無効化する（要件16: 削除は原則行わず無効化方式にする。元に戻す操作ではない旨は画面側で警告する）。"""
    deactivate_application_record(conn, record_id)
    add_event(conn, record_id, "メモ追加", event_title="応募記録を無効化しました")


def get_application_detail(conn: sqlite3.Connection, record_id: int) -> dict | None:
    """応募詳細画面用に、応募履歴に関連する全情報をまとめて取得する。"""
    from src.repositories import (
        get_negotiation_record,
        list_application_results,
        list_client_responses,
        list_follow_up_tasks,
        list_interviews,
        list_timeline,
    )

    record = get_application_record(conn, record_id)
    if record is None:
        return None
    job = get_job(conn, record["job_id"])
    return {
        "record": record, "job": job,
        "status_history": list_status_history(conn, record_id),
        "responses": list_client_responses(conn, record_id),
        "interviews": list_interviews(conn, record_id),
        "negotiation": get_negotiation_record(conn, record_id),
        "results": list_application_results(conn, record_id),
        "follow_ups": list_follow_up_tasks(conn, record_id),
        "timeline": list_timeline(conn, record_id),
    }


def list_application_history(conn: sqlite3.Connection) -> list[dict]:
    return repo_list_application_history(conn)
