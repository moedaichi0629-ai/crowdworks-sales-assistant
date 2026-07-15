"""スコア帯別（総合・AI適合度・安全度・デイリー優先スコア・ポートフォリオ関連度）の分析。"""
from __future__ import annotations

from src.analytics.kpi_service import rate
from src.config import RESULT_TYPE_HIRED

SCORE_BANDS = [
    ("90〜100", 90, 100), ("80〜89", 80, 89), ("70〜79", 70, 79), ("60〜69", 60, 69), ("0〜59", 0, 59),
]


def _band(score: float) -> str | None:
    for label, low, high in SCORE_BANDS:
        if low <= score <= high:
            return label
    return None


def _summarize_applications(items: list[dict]) -> dict:
    total = len(items)
    responded = [r for r in items if (r.get("response_count") or 0) > 0]
    interviewed = [r for r in items if (r.get("interview_count") or 0) > 0]
    hired = [r for r in items if r.get("result_type") == RESULT_TYPE_HIRED]
    contract_amounts = [r["contract_amount"] for r in hired if r.get("contract_amount") is not None]
    return {
        "application_count": total,
        "response_rate": rate(len(responded), total),
        "interview_rate": rate(len(interviewed), total),
        "hired_rate": rate(len(hired), total),
        "contract_amount_total": sum(contract_amounts) if contract_amounts else None,
    }


def _analyze_score_field(
    records: list[dict], score_field: str, jobs: list[dict] | None = None, job_score_field: str | None = None,
) -> dict:
    """応募データをスコア帯へ振り分け、参考として同じ帯に入る「案件数」(全分析済み案件)も付与する。"""
    app_buckets: dict[str, list[dict]] = {label: [] for label, _, _ in SCORE_BANDS}
    for r in records:
        score = r.get(score_field)
        if score is None:
            continue
        band = _band(score)
        if band:
            app_buckets[band].append(r)

    job_counts: dict[str, int] = {label: 0 for label, _, _ in SCORE_BANDS}
    if jobs and job_score_field:
        for j in jobs:
            score = j.get(job_score_field)
            if score is None:
                continue
            band = _band(score)
            if band:
                job_counts[band] += 1

    result: dict[str, dict] = {}
    for label, _, _ in SCORE_BANDS:
        summary = _summarize_applications(app_buckets[label])
        summary["job_count"] = job_counts.get(label, 0)
        result[label] = summary
    return result


def analyze_by_total_score(records: list[dict], jobs: list[dict] | None = None) -> dict:
    return _analyze_score_field(records, "total_score_snapshot", jobs, "total_score")


def analyze_by_ai_score(records: list[dict], jobs: list[dict] | None = None) -> dict:
    return _analyze_score_field(records, "ai_score_snapshot", jobs, "ai_suitability_score")


def analyze_by_safety_score(records: list[dict], jobs: list[dict] | None = None) -> dict:
    return _analyze_score_field(records, "safety_score_snapshot", jobs, "safety_score")


def analyze_by_daily_priority_score(records: list[dict]) -> dict:
    return _analyze_score_field(records, "daily_priority_score_snapshot")


def analyze_by_portfolio_relevance(records: list[dict], avg_relevance: dict) -> dict:
    """応募で使用したポートフォリオの平均関連度スコア帯ごとに成果を集計する（参考値。真の個別値ではない）。"""
    scored: list[dict] = []
    for r in records:
        portfolio_ids = [p.get("id") for p in (r.get("portfolio_snapshot") or []) if p.get("id") is not None]
        scores = [avg_relevance[pid] for pid in portfolio_ids if pid in avg_relevance]
        if scores:
            enriched = dict(r)
            enriched["_relevance_score"] = sum(scores) / len(scores)
            scored.append(enriched)
    return _analyze_score_field(scored, "_relevance_score")
