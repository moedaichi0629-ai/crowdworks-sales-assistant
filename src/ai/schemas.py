"""AI分析レスポンスの構造化スキーマ（案件適合度分析 + 安全性分析を統合）。"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator

from src.config import (
    BUDGET_EVALUATIONS,
    DIFFICULTIES,
    RECOMMENDATIONS,
    RECOMMENDED_ACTIONS,
    RISK_LEVELS,
)


def _clamp(value: int | float, low: int = 0, high: int = 100) -> int:
    try:
        value = int(round(float(value)))
    except (TypeError, ValueError):
        return low
    return max(low, min(high, value))


class AIAnalysisResponse(BaseModel):
    """AIから返される構造化分析結果。値域外・不正な列挙値は安全な既定値へ丸める。"""

    suitability_score: int = 0
    recommendation: str = "consider"
    difficulty: str = "intermediate"
    confidence: int = 0
    summary: str = ""
    client_needs: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    matched_portfolio: list[str] = Field(default_factory=list)
    estimated_hours_min: Optional[int] = None
    estimated_hours_max: Optional[int] = None
    estimated_days: Optional[int] = None
    budget_evaluation: str = "unknown"
    strengths: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    questions_before_applying: list[str] = Field(default_factory=list)
    application_strategy: str = ""
    analysis_reason: str = ""

    safety_score: int = 100
    risk_level: str = "low"
    detected_risks: list[str] = Field(default_factory=list)
    risk_reasons: list[str] = Field(default_factory=list)
    recommended_action: str = "proceed"
    safety_summary: str = ""

    @field_validator("suitability_score", "confidence", "safety_score", mode="before")
    @classmethod
    def _clamp_scores(cls, v):
        return _clamp(v)

    @field_validator("recommendation", mode="before")
    @classmethod
    def _validate_recommendation(cls, v):
        return v if v in RECOMMENDATIONS else "consider"

    @field_validator("difficulty", mode="before")
    @classmethod
    def _validate_difficulty(cls, v):
        return v if v in DIFFICULTIES else "intermediate"

    @field_validator("budget_evaluation", mode="before")
    @classmethod
    def _validate_budget_evaluation(cls, v):
        return v if v in BUDGET_EVALUATIONS else "unknown"

    @field_validator("risk_level", mode="before")
    @classmethod
    def _validate_risk_level(cls, v):
        return v if v in RISK_LEVELS else "low"

    @field_validator("recommended_action", mode="before")
    @classmethod
    def _validate_recommended_action(cls, v):
        return v if v in RECOMMENDED_ACTIONS else "review"

    @field_validator(
        "client_needs", "required_skills", "matched_skills", "missing_skills",
        "matched_portfolio", "strengths", "concerns", "questions_before_applying",
        "detected_risks", "risk_reasons", mode="before",
    )
    @classmethod
    def _coerce_list(cls, v):
        if v is None:
            return []
        if isinstance(v, list):
            return [str(item) for item in v]
        return [str(v)]
