"""クライアント情報別分析、不採用理由・改善点の分析。

自由記述（改善点）はキーワード頻度による単純集計のみとし、外部AIへは送信しない。
"""
from __future__ import annotations

import re

from src.analytics.kpi_service import rate
from src.config import REJECTION_REASONS, RESULT_TYPE_HIRED, RESULT_TYPE_REJECTED

RATING_BANDS = [
    ("評価4.5以上", 4.5, None), ("評価4.0〜4.4", 4.0, 4.49), ("評価3.5〜3.9", 3.5, 3.99), ("評価3.5未満", 0.0, 3.49),
]

APPLICANT_COUNT_BANDS = [
    ("0〜5人", 0, 5), ("6〜10人", 6, 10), ("11〜20人", 11, 20), ("21〜50人", 21, 50), ("51人以上", 51, None),
]

_STOPWORDS = {"こと", "ため", "よう", "これ", "それ", "の", "を", "に", "は", "が", "で", "と", "も", "する", "した"}
_WORD_RE = re.compile(r"[一-龥ぁ-んァ-ヶA-Za-z0-9]{2,}")


def _summarize(items: list[dict]) -> dict:
    total = len(items)
    responded = [r for r in items if (r.get("response_count") or 0) > 0]
    interviewed = [r for r in items if (r.get("interview_count") or 0) > 0]
    hired = [r for r in items if r.get("result_type") == RESULT_TYPE_HIRED]
    return {
        "application_count": total,
        "response_rate": rate(len(responded), total),
        "interview_rate": rate(len(interviewed), total),
        "hired_rate": rate(len(hired), total),
    }


def analyze_by_client_info(records: list[dict]) -> dict:
    """本人確認・クライアント評価・応募人数帯ごとに成果を比較する。"""
    verified: list[dict] = []
    unverified: list[dict] = []
    rating_buckets: dict[str, list[dict]] = {label: [] for label, _, _ in RATING_BANDS}
    rating_buckets["評価なし"] = []
    applicant_buckets: dict[str, list[dict]] = {label: [] for label, _, _ in APPLICANT_COUNT_BANDS}

    recruitment_counts: list[int] = []

    for r in records:
        client = r.get("client_snapshot") or {}
        if client.get("identity_verified"):
            verified.append(r)
        else:
            unverified.append(r)

        rating = client.get("client_rating")
        if rating is None:
            rating_buckets["評価なし"].append(r)
        else:
            for label, low, high in RATING_BANDS:
                if rating >= low and (high is None or rating <= high):
                    rating_buckets[label].append(r)
                    break

        applicant_count = r.get("applicant_count_snapshot")
        if applicant_count is not None:
            for label, low, high in APPLICANT_COUNT_BANDS:
                if applicant_count >= low and (high is None or applicant_count <= high):
                    applicant_buckets[label].append(r)
                    break

        recruitment_count = (r.get("job_snapshot") or {}).get("recruitment_count")
        if recruitment_count is not None:
            recruitment_counts.append(recruitment_count)

    return {
        "identity_verified": _summarize(verified),
        "identity_unverified": _summarize(unverified),
        "by_rating": {label: _summarize(items) for label, items in rating_buckets.items() if items},
        "by_applicant_count": {label: _summarize(items) for label, items in applicant_buckets.items() if items},
        "avg_recruitment_count": (
            round(sum(recruitment_counts) / len(recruitment_counts), 1) if recruitment_counts else None
        ),
    }


def analyze_rejection_reasons(records: list[dict]) -> dict:
    """不採用理由ごとの件数を集計する。"""
    rejected = [r for r in records if r.get("result_type") == RESULT_TYPE_REJECTED]
    counts = {reason: 0 for reason in REJECTION_REASONS}
    for r in rejected:
        reason = r.get("client_reason")
        if reason in counts:
            counts[reason] += 1
        elif reason:
            counts["その他"] = counts.get("その他", 0) + 1
    return {"total_rejected": len(rejected), "by_reason": {k: v for k, v in counts.items() if v > 0}}


def analyze_improvement_points(records: list[dict], top_n: int = 15) -> list[tuple[str, int]]:
    """改善点の自由記述から、頻出キーワードを単純集計する（外部AIは使用しない）。"""
    word_counts: dict[str, int] = {}
    for r in records:
        for point in (r.get("improvement_points") or []):
            for word in _WORD_RE.findall(str(point)):
                if word in _STOPWORDS:
                    continue
                word_counts[word] = word_counts.get(word, 0) + 1
    return sorted(word_counts.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
