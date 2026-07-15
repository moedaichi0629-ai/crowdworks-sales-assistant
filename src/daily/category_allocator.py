"""案件をAI・開発／デザイン／その他へ分類し、本日の候補選定で使うジャンル別配分を扱う。

第3段階のポートフォリオ用分類（portfolio_category_classifier）とは目的が異なり、
1日の応募候補をジャンルへ偏りなく振り分けるための、より単純な多数決分類を行う。
"""
from __future__ import annotations

from src.config import (
    CATEGORY_GROUP_AI_DEV,
    CATEGORY_GROUP_DESIGN,
    CATEGORY_GROUP_OTHER,
    DAILY_AI_DEV_KEYWORDS,
    DAILY_DESIGN_KEYWORDS,
    DAILY_OTHER_KEYWORDS,
)

_ORDERED_GROUPS = [CATEGORY_GROUP_AI_DEV, CATEGORY_GROUP_DESIGN, CATEGORY_GROUP_OTHER]


def _job_text(job: dict) -> str:
    return " ".join(str(job.get(field) or "") for field in ("title", "category", "description", "body"))


def classify_category_group(job: dict) -> str:
    """案件をAI・開発／デザイン／その他のいずれかへ分類する。

    キーワード一致数が最も多いジャンルを採用し、同数の場合は
    AI・開発 > デザイン > その他 の優先順で決定する。一致が無ければ「その他」とする。
    """
    text = _job_text(job)
    counts = {
        CATEGORY_GROUP_AI_DEV: sum(1 for kw in DAILY_AI_DEV_KEYWORDS if kw and kw in text),
        CATEGORY_GROUP_DESIGN: sum(1 for kw in DAILY_DESIGN_KEYWORDS if kw and kw in text),
        CATEGORY_GROUP_OTHER: sum(1 for kw in DAILY_OTHER_KEYWORDS if kw and kw in text),
    }
    if all(c == 0 for c in counts.values()):
        return CATEGORY_GROUP_OTHER
    return max(_ORDERED_GROUPS, key=lambda g: counts[g])


def validate_allocation(target_count: int, ai_development_target: int, design_target: int, other_target: int) -> tuple[bool, int]:
    """ジャンル別件数の合計が本日の応募目標(target_count)と一致するか検証する。

    戻り値: (一致するか, 合計値)
    """
    total = int(ai_development_target) + int(design_target) + int(other_target)
    return total == int(target_count), total


def allocation_targets(goal: dict) -> dict[str, int]:
    """応募目標(daily_application_goals行)からジャンル別の本日の枠数を取得する。"""
    return {
        CATEGORY_GROUP_AI_DEV: int(goal.get("ai_development_target", 0) or 0),
        CATEGORY_GROUP_DESIGN: int(goal.get("design_target", 0) or 0),
        CATEGORY_GROUP_OTHER: int(goal.get("other_target", 0) or 0),
    }
