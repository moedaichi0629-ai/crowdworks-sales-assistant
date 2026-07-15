"""条件相談(negotiation_service)・結果管理(result_service)のテスト。"""
from __future__ import annotations

from src.config import APP_STATUS_HIRED, APP_STATUS_NEGOTIATING, APP_STATUS_REJECTED, APP_STATUS_WITHDRAWN
from src.crm.application_history_service import create_application_history, get_application_detail
from src.crm.negotiation_service import get_negotiation, save_negotiation
from src.crm.result_service import get_result, record_hired, record_rejected, record_withdrawn
from src.database import session
from src.repositories import insert_job


def _insert_record(db_path, price=30000) -> int:
    with session(db_path) as conn:
        job_id = insert_job(conn, {"title": "条件相談テスト案件", "source_type": "manual"})
        return create_application_history(conn, job_id, proposed_price=price)


def test_save_negotiation_updates_price_and_delivery(db_path):
    record_id = _insert_record(db_path)
    with session(db_path) as conn:
        save_negotiation(conn, record_id, {
            "original_price": 30000, "client_offered_price": 25000, "agreed_price": 28000,
            "original_delivery_date": "2026-08-01", "requested_delivery_date": "2026-08-10",
            "agreed_delivery_date": "2026-08-05", "agreement_status": "合意",
        })

    with session(db_path) as conn:
        negotiation = get_negotiation(conn, record_id)
    assert negotiation["agreed_price"] == 28000
    assert negotiation["agreed_delivery_date"] == "2026-08-05"


def test_save_negotiation_twice_updates_same_row(db_path):
    record_id = _insert_record(db_path)
    with session(db_path) as conn:
        save_negotiation(conn, record_id, {"agreed_price": 25000, "agreement_status": "相談中"})
        save_negotiation(conn, record_id, {"agreed_price": 28000, "agreement_status": "合意"})

    with session(db_path) as conn:
        negotiation = get_negotiation(conn, record_id)
    assert negotiation["agreed_price"] == 28000
    assert negotiation["agreement_status"] == "合意"


def test_negotiating_status_syncs_application_status(db_path):
    record_id = _insert_record(db_path)
    with session(db_path) as conn:
        save_negotiation(conn, record_id, {"agreement_status": "相談中"})
    with session(db_path) as conn:
        detail = get_application_detail(conn, record_id)
    assert detail["record"]["application_status"] == APP_STATUS_NEGOTIATING


def test_record_hired_saves_contract_amount(db_path):
    record_id = _insert_record(db_path)
    with session(db_path) as conn:
        record_hired(conn, record_id, contract_amount=45000, contract_type="固定報酬", is_recurring=True)

    with session(db_path) as conn:
        result = get_result(conn, record_id)
        detail = get_application_detail(conn, record_id)
    assert result["result_type"] == "採用"
    assert result["contract_amount"] == 45000
    assert result["is_recurring"] is True
    assert detail["record"]["application_status"] == APP_STATUS_HIRED


def test_record_rejected_saves_reason_and_improvement_points(db_path):
    record_id = _insert_record(db_path)
    with session(db_path) as conn:
        record_rejected(conn, record_id, client_reason="金額", improvement_points=["単価をもう少し下げる余地を検討する"])

    with session(db_path) as conn:
        result = get_result(conn, record_id)
        detail = get_application_detail(conn, record_id)
    assert result["result_type"] == "不採用"
    assert result["client_reason"] == "金額"
    assert result["improvement_points"] == ["単価をもう少し下げる余地を検討する"]
    assert detail["record"]["application_status"] == APP_STATUS_REJECTED


def test_record_withdrawn_saves_reason(db_path):
    record_id = _insert_record(db_path)
    with session(db_path) as conn:
        record_withdrawn(conn, record_id, withdrawal_reason="他の案件を優先するため")

    with session(db_path) as conn:
        result = get_result(conn, record_id)
        detail = get_application_detail(conn, record_id)
    assert result["result_type"] == "辞退"
    assert result["withdrawal_reason"] == "他の案件を優先するため"
    assert detail["record"]["application_status"] == APP_STATUS_WITHDRAWN
