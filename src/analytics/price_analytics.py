"""応募金額帯・納期帯ごとの成果分析。固定報酬と時間単価を分けて分析する。"""
from __future__ import annotations

from src.analytics.category_analytics import classify_record_category_group
from src.analytics.kpi_service import rate
from src.config import CONTRACT_TYPE_FIXED, CONTRACT_TYPE_HOURLY, RESULT_TYPE_HIRED

PRICE_BANDS = [
    ("〜3,000円", 0, 3000),
    ("3,001〜5,000円", 3001, 5000),
    ("5,001〜10,000円", 5001, 10000),
    ("10,001〜30,000円", 10001, 30000),
    ("30,001〜50,000円", 30001, 50000),
    ("50,001円以上", 50001, None),
]

DELIVERY_BANDS = [
    ("1〜3日", 1, 3),
    ("4〜7日", 4, 7),
    ("8〜14日", 8, 14),
    ("15〜30日", 15, 30),
    ("31日以上", 31, None),
]


def _price_band(price: int) -> str | None:
    for label, low, high in PRICE_BANDS:
        if price >= low and (high is None or price <= high):
            return label
    return None


def _delivery_band(days: int) -> str | None:
    for label, low, high in DELIVERY_BANDS:
        if days >= low and (high is None or days <= high):
            return label
    return None


def _contract_type_of(record: dict) -> str:
    """CRM側で契約種別が未入力の場合は、案件の募集形式(job_snapshot)から推定する。"""
    if record.get("contract_type"):
        return record["contract_type"]
    job_type = (record.get("job_snapshot") or {}).get("job_type") or ""
    if "時間単価" in job_type:
        return CONTRACT_TYPE_HOURLY
    return CONTRACT_TYPE_FIXED


def _summarize(items: list[dict]) -> dict:
    total = len(items)
    responded = [r for r in items if (r.get("response_count") or 0) > 0]
    interviewed = [r for r in items if (r.get("interview_count") or 0) > 0]
    hired = [r for r in items if r.get("result_type") == RESULT_TYPE_HIRED]
    contract_amounts = [r["contract_amount"] for r in hired if r.get("contract_amount") is not None]

    price_diffs = [
        r["contract_amount"] - r["proposed_price"] for r in hired
        if r.get("contract_amount") is not None and r.get("proposed_price") is not None
    ]

    return {
        "application_count": total,
        "response_rate": rate(len(responded), total),
        "interview_rate": rate(len(interviewed), total),
        "hired_rate": rate(len(hired), total),
        "contract_amount_total": sum(contract_amounts) if contract_amounts else None,
        "avg_price_vs_contract_diff": round(sum(price_diffs) / len(price_diffs)) if price_diffs else None,
    }


def analyze_by_price_band(records: list[dict]) -> dict:
    """応募金額帯ごと・契約種別（固定報酬/時間単価）ごとに成果を集計する。"""
    result: dict[str, dict] = {}
    for contract_type in (CONTRACT_TYPE_FIXED, CONTRACT_TYPE_HOURLY):
        buckets: dict[str, list[dict]] = {label: [] for label, _, _ in PRICE_BANDS}
        for r in records:
            if _contract_type_of(r) != contract_type:
                continue
            price = r.get("proposed_price")
            if price is None:
                continue
            band = _price_band(int(price))
            if band:
                buckets[band].append(r)
        result[contract_type] = {label: _summarize(items) for label, items in buckets.items() if items}
    return result


def analyze_by_delivery_band(records: list[dict]) -> dict:
    """提案納期の長さごとに成果を集計する（ジャンル別の内訳付き）。"""
    buckets: dict[str, list[dict]] = {label: [] for label, _, _ in DELIVERY_BANDS}
    for r in records:
        days = r.get("proposed_delivery_days")
        if days is None:
            continue
        band = _delivery_band(int(days))
        if band:
            buckets[band].append(r)

    result: dict[str, dict] = {}
    for label, items in buckets.items():
        if not items:
            continue
        summary = _summarize(items)
        by_category: dict[str, int] = {}
        for r in items:
            group = classify_record_category_group(r)
            by_category[group] = by_category.get(group, 0) + 1
        summary["by_category_group"] = by_category
        result[label] = summary
    return result
