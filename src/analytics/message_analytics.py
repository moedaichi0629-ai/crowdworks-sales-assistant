"""営業文タイプ（トーン）別の成果分析。母数が少ない分類は「参考値」として明示する。"""
from __future__ import annotations

from src.analytics.kpi_service import rate
from src.config import GENERATION_TONES, RESULT_TYPE_HIRED

# 母数がこれ未満の分類は「参考値」として明示する（要件6の初期基準）
LOW_SAMPLE_THRESHOLD = 5


def analyze_by_tone(records: list[dict]) -> dict:
    """営業文タイプ（トーン）ごとの使用回数・成果を集計する。"""
    buckets: dict[str, list[dict]] = {tone: [] for tone in GENERATION_TONES}
    for r in records:
        tone = r.get("tone")
        if tone:
            buckets.setdefault(tone, []).append(r)

    result: dict[str, dict] = {}
    for tone, items in buckets.items():
        if not items:
            continue
        total = len(items)
        responded = [r for r in items if (r.get("response_count") or 0) > 0]
        interviewed = [r for r in items if (r.get("interview_count") or 0) > 0]
        hired = [r for r in items if r.get("result_type") == RESULT_TYPE_HIRED]
        contract_amounts = [r["contract_amount"] for r in hired if r.get("contract_amount") is not None]
        lengths = [len(r["sent_message"]) for r in items if r.get("sent_message")]
        prices = [r["proposed_price"] for r in items if r.get("proposed_price") is not None]
        total_scores = [r["total_score_snapshot"] for r in items if r.get("total_score_snapshot") is not None]

        result[tone] = {
            "usage_count": total,
            "response_rate": rate(len(responded), total),
            "interview_rate": rate(len(interviewed), total),
            "hired_rate": rate(len(hired), total),
            "contract_amount_total": sum(contract_amounts) if contract_amounts else None,
            "avg_message_length": round(sum(lengths) / len(lengths)) if lengths else None,
            "avg_proposed_price": round(sum(prices) / len(prices)) if prices else None,
            "avg_total_score": round(sum(total_scores) / len(total_scores), 1) if total_scores else None,
            "is_reference_only": total < LOW_SAMPLE_THRESHOLD,
        }
    return result
