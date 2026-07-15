"""ジャンル別（AI・開発／デザイン／その他）の成果比較・細分類分析。"""
from __future__ import annotations

from src.analytics.kpi_service import rate
from src.config import CATEGORY_GROUP_AI_DEV, CATEGORY_GROUP_DESIGN, CATEGORY_GROUP_OTHER
from src.config import RESULT_TYPE_HIRED
from src.daily.category_allocator import classify_category_group

# ジャンル別分析における細分類（案件タイトル・カテゴリ文字列とのキーワード一致で判定する簡易分類）
SUBCATEGORY_KEYWORDS: dict[str, list[str]] = {
    "AI開発": ["AI開発", "AIツール", "ChatGPT", "OpenAI API", "Dify"],
    "API連携": ["API連携", "Google API", "外部API"],
    "業務自動化": ["業務自動化", "自動化", "GAS", "Google Apps Script"],
    "Webアプリ": ["Webアプリ", "アプリ開発", "システム開発"],
    "ホームページ制作": ["ホームページ", "HP制作", "LP制作", "サイト制作", "Webサイト"],
    "チャットボット": ["チャットボット", "ボット開発", "LINE連携"],
    "バナー": ["バナー"],
    "SNS画像": ["SNS投稿画像", "SNS画像", "Instagram投稿"],
    "サムネイル": ["サムネイル", "YouTubeサムネイル"],
    "ロゴ": ["ロゴ"],
    "名刺": ["名刺"],
    "チラシ": ["チラシ", "フライヤー"],
    "Webデザイン": ["Webデザイン"],
    "LPデザイン": ["LPデザイン"],
}


def _job_text(record: dict) -> str:
    snapshot = record.get("job_snapshot") or {}
    return " ".join(str(snapshot.get(f) or "") for f in ("title", "category"))


def _pseudo_job(record: dict) -> dict:
    snapshot = record.get("job_snapshot") or {}
    return {"title": snapshot.get("title"), "category": snapshot.get("category"), "description": "", "body": ""}


def classify_record_category_group(record: dict) -> str:
    return classify_category_group(_pseudo_job(record))


def classify_record_subcategories(record: dict) -> list[str]:
    text = _job_text(record)
    return [name for name, keywords in SUBCATEGORY_KEYWORDS.items() if any(kw in text for kw in keywords)]


def _summarize(records: list[dict]) -> dict:
    total = len(records)
    responded = [r for r in records if (r.get("response_count") or 0) > 0]
    interviewed = [r for r in records if (r.get("interview_count") or 0) > 0]
    hired = [r for r in records if r.get("result_type") == RESULT_TYPE_HIRED]
    contract_amounts = [r["contract_amount"] for r in hired if r.get("contract_amount") is not None]
    prices = [r["proposed_price"] for r in records if r.get("proposed_price") is not None]
    total_scores = [r["total_score_snapshot"] for r in records if r.get("total_score_snapshot") is not None]
    safety_scores = [r["safety_score_snapshot"] for r in records if r.get("safety_score_snapshot") is not None]

    return {
        "application_count": total,
        "response_count": len(responded),
        "response_rate": rate(len(responded), total),
        "interview_count": len(interviewed),
        "interview_rate": rate(len(interviewed), total),
        "hired_count": len(hired),
        "hired_rate": rate(len(hired), total),
        "contract_amount_total": sum(contract_amounts) if contract_amounts else None,
        "contract_amount_avg": round(sum(contract_amounts) / len(contract_amounts)) if contract_amounts else None,
        "avg_proposed_price": round(sum(prices) / len(prices)) if prices else None,
        "avg_total_score": round(sum(total_scores) / len(total_scores), 1) if total_scores else None,
        "avg_safety_score": round(sum(safety_scores) / len(safety_scores), 1) if safety_scores else None,
    }


def analyze_by_category_group(records: list[dict]) -> dict:
    """AI・開発／デザイン／その他の大分類ごとに成果を比較する。"""
    groups: dict[str, list[dict]] = {
        CATEGORY_GROUP_AI_DEV: [], CATEGORY_GROUP_DESIGN: [], CATEGORY_GROUP_OTHER: [],
    }
    for r in records:
        groups[classify_record_category_group(r)].append(r)

    return {group: _summarize(items) for group, items in groups.items()}


def analyze_by_subcategory(records: list[dict]) -> dict:
    """細分類（AI開発/API連携/… バナー/ロゴ/…）ごとに成果を集計する。1件が複数分類に該当してよい。"""
    buckets: dict[str, list[dict]] = {name: [] for name in SUBCATEGORY_KEYWORDS}
    for r in records:
        for name in classify_record_subcategories(r):
            buckets[name].append(r)

    return {name: _summarize(items) for name, items in buckets.items() if items}
