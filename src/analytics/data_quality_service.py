"""分析の信頼性を確認するためのデータ品質チェック。"""
from __future__ import annotations

from src.config import APP_STATUS_UNKNOWN, RESULT_TYPE_HIRED, RESULT_TYPE_REJECTED


def check_data_quality(records: list[dict]) -> dict:
    """入力不足・欠損データの状況を集計する（分析結果の信頼性確認用）。"""
    total = len(records)
    with_result = [r for r in records if r.get("result_type")]
    unknown_status = [r for r in records if r.get("application_status") == APP_STATUS_UNKNOWN]

    hired = [r for r in records if r.get("result_type") == RESULT_TYPE_HIRED]
    hired_missing_amount = [r for r in hired if r.get("contract_amount") is None]

    rejected = [r for r in records if r.get("result_type") == RESULT_TYPE_REJECTED]
    rejected_missing_reason = [r for r in rejected if not r.get("client_reason")]

    missing_portfolio = [r for r in records if not (r.get("portfolio_snapshot") or [])]
    missing_tone = [r for r in records if not r.get("tone")]

    return {
        "total_records": total,
        "result_input_rate": round(len(with_result) / total * 100, 1) if total else None,
        "unknown_status_count": len(unknown_status),
        "hired_missing_contract_amount_count": len(hired_missing_amount),
        "rejected_missing_reason_count": len(rejected_missing_reason),
        "missing_portfolio_snapshot_count": len(missing_portfolio),
        "missing_tone_count": len(missing_tone),
    }
