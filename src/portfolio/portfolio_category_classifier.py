"""案件本文からデザイン系・開発系・AI×デザイン複合系のいずれかを判定する。

ポートフォリオ自動選択（portfolio_matcher）の入力として利用する。
キーワード一致のみの単純な分類であり、複数カテゴリに同時該当してよい
（AI×デザイン複合案件では開発系・デザイン系の両方に該当し得る）。
"""
from __future__ import annotations

from src.config import (
    DEFAULT_AI_DESIGN_JOB_KEYWORDS,
    DEFAULT_DESIGN_JOB_KEYWORDS,
    DEFAULT_DEVELOPMENT_JOB_KEYWORDS,
)

CATEGORY_DESIGN = "design"
CATEGORY_DEVELOPMENT = "development"
CATEGORY_AI_DESIGN = "ai_design"


def _job_text(job: dict) -> str:
    return " ".join(
        str(job.get(field) or "") for field in ("title", "category", "description", "body")
    )


def classify_job_category(job: dict) -> dict:
    """案件がデザイン系・開発系・AI×デザイン複合系のどれに該当するかを判定する。

    戻り値: {
        "is_design": bool, "is_development": bool, "is_ai_design": bool,
        "matched_design_keywords": [...], "matched_development_keywords": [...],
        "matched_ai_design_keywords": [...],
    }
    """
    text = _job_text(job)

    matched_design = [kw for kw in DEFAULT_DESIGN_JOB_KEYWORDS if kw and kw in text]
    matched_development = [kw for kw in DEFAULT_DEVELOPMENT_JOB_KEYWORDS if kw and kw in text]
    matched_ai_design = [kw for kw in DEFAULT_AI_DESIGN_JOB_KEYWORDS if kw and kw in text]

    is_ai_design = bool(matched_ai_design) or (bool(matched_design) and bool(matched_development))

    return {
        "is_design": bool(matched_design),
        "is_development": bool(matched_development),
        "is_ai_design": is_ai_design,
        "matched_design_keywords": matched_design,
        "matched_development_keywords": matched_development,
        "matched_ai_design_keywords": matched_ai_design,
    }
