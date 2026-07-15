"""ポートフォリオ別の成果分析。

1件の応募で複数のポートフォリオを使用した場合、それぞれの使用回数へ含める。
このため、ここでの数値は「そのポートフォリオ単独の効果」を証明するものではなく、
あくまで参考傾向として扱うこと（要件7）。
"""
from __future__ import annotations

import sqlite3

from src.analytics.kpi_service import rate
from src.config import RESULT_TYPE_HIRED
from src.repositories import get_portfolio_average_relevance


def analyze_by_portfolio(conn: sqlite3.Connection, records: list[dict]) -> dict:
    """ポートフォリオごと（タイトル別）の使用回数・成果を集計する。"""
    buckets: dict[str, dict] = {}
    avg_relevance = get_portfolio_average_relevance(conn)

    for r in records:
        for p in (r.get("portfolio_snapshot") or []):
            title = p.get("title") or f"ポートフォリオID{p.get('id')}"
            bucket = buckets.setdefault(title, {"portfolio_id": p.get("id"), "records": [], "categories": set()})
            bucket["records"].append(r)
            snapshot_category = (r.get("job_snapshot") or {}).get("category")
            if snapshot_category:
                bucket["categories"].add(snapshot_category)

    result: dict[str, dict] = {}
    for title, bucket in buckets.items():
        items = bucket["records"]
        total = len(items)
        responded = [r for r in items if (r.get("response_count") or 0) > 0]
        interviewed = [r for r in items if (r.get("interview_count") or 0) > 0]
        hired = [r for r in items if r.get("result_type") == RESULT_TYPE_HIRED]
        contract_amounts = [r["contract_amount"] for r in hired if r.get("contract_amount") is not None]

        result[title] = {
            "usage_count": total,
            "response_count": len(responded),
            "response_rate": rate(len(responded), total),
            "interview_count": len(interviewed),
            "interview_rate": rate(len(interviewed), total),
            "hired_count": len(hired),
            "hired_rate": rate(len(hired), total),
            "contract_amount_total": sum(contract_amounts) if contract_amounts else None,
            "used_categories": sorted(bucket["categories"]),
            "avg_relevance_score": avg_relevance.get(bucket["portfolio_id"]),
        }
    return result
