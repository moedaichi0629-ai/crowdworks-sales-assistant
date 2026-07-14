"""案件の作業量・稼働時間から納期を提案する。

対応が難しい場合は無理に短納期を提示せず、事前確認事項・警告として扱う
（要件の「納期の提案」に対応）。
"""
from __future__ import annotations

import math
import re

from src.config import DEFAULT_DELIVERY_SETTINGS

_DESIGN_KEYWORDS = [
    "バナー", "ロゴ", "チラシ", "名刺", "デザイン", "サムネイル", "SNS投稿画像", "資料デザイン", "スライド",
]
_MATERIAL_WAIT_KEYWORDS = ["素材", "画像提供", "文章提供", "原稿", "写真提供"]
_API_REVIEW_KEYWORDS = ["LINE", "API", "外部サービス", "審査"]
_DIFFICULT_DIFFICULTIES = {"advanced", "expert"}


def _job_text(job: dict) -> str:
    return " ".join(str(job.get(field) or "") for field in ("title", "category", "description", "body"))


def _parse_daily_hours(daily_available_hours: str | float | None, default: float) -> float:
    if isinstance(daily_available_hours, (int, float)):
        return float(daily_available_hours)
    if not daily_available_hours:
        return default
    numbers = re.findall(r"\d+(?:\.\d+)?", str(daily_available_hours))
    if not numbers:
        return default
    values = [float(n) for n in numbers]
    return sum(values) / len(values)


def compute_delivery_suggestion(
    job: dict,
    estimated_hours_min: int | None = None,
    estimated_hours_max: int | None = None,
    estimated_days: int | None = None,
    difficulty: str | None = None,
    daily_available_hours: str | float | None = None,
    concurrent_job_count: int = 0,
    delivery_settings: dict | None = None,
) -> dict:
    """納期の提案を算出する。

    戻り値: {"minimum_delivery_days", "safe_delivery_days", "recommended_delivery_days",
              "required_work_days", "delivery_reason", "pre_confirmation_items", "warnings"}
    """
    settings = {**DEFAULT_DELIVERY_SETTINGS, **(delivery_settings or {})}
    text = _job_text(job)
    daily_hours = _parse_daily_hours(daily_available_hours, settings["daily_available_hours_default"])

    reasons: list[str] = []
    pre_confirmation: list[str] = []
    warnings: list[str] = []

    hours_mid = None
    if estimated_hours_min is not None and estimated_hours_max is not None:
        hours_mid = (estimated_hours_min + estimated_hours_max) / 2
    elif estimated_hours_min is not None or estimated_hours_max is not None:
        hours_mid = estimated_hours_min or estimated_hours_max
    elif estimated_days is not None:
        hours_mid = estimated_days * daily_hours

    if hours_mid is None:
        required_work_days = 3.0
        reasons.append("予想作業時間が不明なため、標準的な想定作業日数（3日）を基準に算出")
        warnings.append("作業内容が確定していないため、対応可否・納期は応募後にすり合わせることをおすすめします。")
    else:
        required_work_days = hours_mid / daily_hours if daily_hours > 0 else hours_mid
        reasons.append(f"予想作業時間 約{hours_mid:.1f}時間 ÷ 1日あたり稼働時間 約{daily_hours:.1f}時間 で算出")

    buffer_days = settings["buffer_days_standard"]

    if any(k in text for k in _DESIGN_KEYWORDS):
        buffer_days += settings["design_draft_buffer_days"] + settings["revision_buffer_days"]
        reasons.append("デザイン案の作成・初稿提出・修正対応のバッファを加算")
        pre_confirmation.append("デザイン案の確認・修正回数の上限")

    if any(k in text for k in _MATERIAL_WAIT_KEYWORDS):
        buffer_days += settings["material_wait_buffer_days"]
        reasons.append("素材・原稿の受領待ちバッファを加算")
        pre_confirmation.append("素材（画像・文章等）の提供タイミング")

    if any(k in text for k in _API_REVIEW_KEYWORDS):
        buffer_days += settings["api_review_buffer_days"]
        reasons.append("外部サービス設定・API審査待ちバッファを加算")
        pre_confirmation.append("外部サービス（API等）の審査・設定に必要な期間")

    if concurrent_job_count > 0:
        extra = min(concurrent_job_count, 3)
        buffer_days += extra
        reasons.append(f"他案件を同時進行中のため+{extra}日のバッファを加算")

    minimum_delivery_days = max(1, math.ceil(required_work_days) + settings["buffer_days_min"])
    safe_delivery_days = max(minimum_delivery_days, math.ceil(required_work_days) + buffer_days)
    recommended_delivery_days = safe_delivery_days

    if difficulty in _DIFFICULT_DIFFICULTIES:
        warnings.append("難易度が高い案件のため、対応可能と断定せず、事前に技術面の確認をおすすめします。")

    days_left = None
    deadline = job.get("deadline")
    if deadline:
        import datetime as dt
        try:
            deadline_date = dt.datetime.strptime(str(deadline)[:10], "%Y-%m-%d").date()
            days_left = (deadline_date - dt.date.today()).days
        except ValueError:
            days_left = None

    if days_left is not None and days_left < recommended_delivery_days:
        warnings.append(
            f"案件の応募期限までの残り日数（約{days_left}日）が推奨納期（{recommended_delivery_days}日）より短いため、"
            "納期の調整可否を事前に確認することをおすすめします。"
        )

    return {
        "minimum_delivery_days": minimum_delivery_days,
        "safe_delivery_days": safe_delivery_days,
        "recommended_delivery_days": recommended_delivery_days,
        "required_work_days": round(required_work_days, 1),
        "delivery_reason": " / ".join(reasons),
        "pre_confirmation_items": pre_confirmation,
        "warnings": warnings,
    }
