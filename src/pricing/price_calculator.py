"""案件情報・予想作業時間・難易度から応募金額を提案する。

案件の予算範囲を尊重しつつ、最低受注金額を下回らないようにし、
極端な値下げを避ける（要件の「応募金額の提案」に対応）。
作業内容が不明確な場合は確定金額を断定せず、目安であることを明記する。
"""
from __future__ import annotations

from src.config import DEFAULT_PRICING_SETTINGS

_WEBSITE_KEYWORDS = ["ホームページ制作", "ホームページ", "LP制作", "LPデザイン", "サイト制作", "Webサイト"]
_HOURLY_JOB_TYPES = {"時間単価制"}
_AI_API_KEYWORDS = ["AI", "API連携", "ChatGPT", "OpenAI", "Claude", "Gemini", "Dify", "自動化"]
_DATA_ENTRY_KEYWORDS = ["データ入力", "リサーチ"]


def _job_text(job: dict) -> str:
    return " ".join(str(job.get(field) or "") for field in ("title", "category", "description", "body"))


def _budget_midpoint(job: dict) -> int | None:
    bmin, bmax = job.get("budget_min"), job.get("budget_max")
    if bmin is not None and bmax is not None:
        return round((bmin + bmax) / 2)
    return bmax if bmax is not None else bmin


def compute_price_suggestion(
    job: dict,
    estimated_hours_min: int | None = None,
    estimated_hours_max: int | None = None,
    difficulty: str | None = None,
    pricing_settings: dict | None = None,
) -> dict:
    """応募金額の提案を算出する。

    戻り値: {"proposed_price", "minimum_price", "ideal_price", "price_reason", "is_uncertain"}
    金額は目安であり、作業内容が確定していない場合は is_uncertain=True とし、
    price_reason に「目安」であることを明記する。
    """
    settings = {**DEFAULT_PRICING_SETTINGS, **(pricing_settings or {})}
    text = _job_text(job)
    reasons: list[str] = []
    is_uncertain = False

    minimum_order = settings["minimum_order_price_yen"]
    budget_mid = _budget_midpoint(job)

    # --- 時間単価制の案件: 時給そのものを提案する ---
    if job.get("job_type") in _HOURLY_JOB_TYPES:
        if any(k in text for k in _AI_API_KEYWORDS):
            proposed = max(settings["ai_api_hourly_rate_min"], settings["base_hourly_rate_yen"])
            reasons.append(f"AI・API連携案件の時給目安（{settings['ai_api_hourly_rate_min']}〜{settings['ai_api_hourly_rate_max']}円）を採用")
        else:
            proposed = settings["base_hourly_rate_yen"]
            reasons.append(f"基準時間単価（{settings['base_hourly_rate_yen']}円/時間）を採用")
        minimum = max(minimum_order, round(proposed * 0.85))
        ideal = round(proposed * 1.15)
        return {
            "proposed_price": proposed, "minimum_price": minimum, "ideal_price": ideal,
            "price_reason": " / ".join(reasons), "is_uncertain": False,
        }

    # --- ホームページ・LP制作: 最低金額を設定 ---
    if any(k in text for k in _WEBSITE_KEYWORDS):
        floor = settings["website_minimum_price_yen"]
        proposed = max(floor, budget_mid or floor)
        reasons.append(f"ホームページ・LP制作の基本最低金額（{floor}円）を基準に算出")
        minimum = floor
        ideal = round(proposed * 1.2)
        if job.get("budget_max") and proposed > job["budget_max"]:
            proposed = job["budget_max"]
            reasons.append("案件の予算上限に合わせて調整")
        return {
            "proposed_price": proposed, "minimum_price": minimum, "ideal_price": ideal,
            "price_reason": " / ".join(reasons), "is_uncertain": False,
        }

    # --- カテゴリ別の目安（デザイン系・データ入力等）---
    for category_name, note in settings.get("category_price_notes", {}).items():
        if category_name in text:
            base = budget_mid or minimum_order
            proposed = max(minimum_order, base)
            reasons.append(f"「{category_name}」の目安: {note}")
            is_uncertain = True
            minimum = minimum_order
            ideal = round(proposed * 1.2)
            return {
                "proposed_price": proposed, "minimum_price": minimum, "ideal_price": ideal,
                "price_reason": " / ".join(reasons) + "（枚数・内容により変動するため目安です）",
                "is_uncertain": is_uncertain,
            }

    # --- 固定報酬制で予想作業時間が分かる場合: 時給換算 ---
    if estimated_hours_min is not None or estimated_hours_max is not None:
        hours_mid = None
        if estimated_hours_min is not None and estimated_hours_max is not None:
            hours_mid = (estimated_hours_min + estimated_hours_max) / 2
        else:
            hours_mid = estimated_hours_min or estimated_hours_max

        rate = settings["base_hourly_rate_yen"]
        if any(k in text for k in _AI_API_KEYWORDS):
            rate = (settings["ai_api_hourly_rate_min"] + settings["ai_api_hourly_rate_max"]) / 2
        proposed = max(minimum_order, round(hours_mid * rate))
        reasons.append(f"予想作業時間 約{hours_mid:.1f}時間 × 時給目安{round(rate)}円で算出")
        if job.get("budget_max") and proposed > job["budget_max"]:
            reasons.append("案件の予算上限内に収まるよう調整")
            proposed = max(minimum_order, job["budget_max"])
        minimum = max(minimum_order, round(proposed * 0.85))
        ideal = round(proposed * 1.15)
        return {
            "proposed_price": proposed, "minimum_price": minimum, "ideal_price": ideal,
            "price_reason": " / ".join(reasons), "is_uncertain": False,
        }

    # --- 情報が不足している場合: 予算の目安 or 最低受注金額から断定を避けて提示 ---
    proposed = budget_mid or minimum_order
    proposed = max(minimum_order, proposed)
    reasons.append("作業内容の詳細が確認できないため、予算相場を参考にした目安金額です（確定額ではありません）")
    return {
        "proposed_price": proposed, "minimum_price": minimum_order, "ideal_price": round(proposed * 1.2),
        "price_reason": " / ".join(reasons), "is_uncertain": True,
    }
