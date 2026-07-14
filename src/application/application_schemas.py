"""営業文生成AIレスポンスの構造化スキーマ。"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


def _clamp_int(value, low: int = 0, high: int = 10_000_000) -> int:
    try:
        value = int(round(float(value)))
    except (TypeError, ValueError):
        return low
    return max(low, min(high, value))


class ApplicationDraftResponse(BaseModel):
    """AIから返される営業文生成結果。不足項目は安全な既定値で補完する。"""

    application_title: str = ""
    opening: str = ""
    understanding: str = ""
    matching_reason: str = ""
    skills_to_highlight: list[str] = Field(default_factory=list)
    portfolio_ids: list[int] = Field(default_factory=list)
    portfolio_reasons: list[str] = Field(default_factory=list)
    proposed_approach: list[str] = Field(default_factory=list)
    proposed_price: int = 0
    price_reason: str = ""
    proposed_delivery_days: int = 0
    delivery_reason: str = ""
    answers_to_client_questions: list[str] = Field(default_factory=list)
    questions_for_client: list[str] = Field(default_factory=list)
    closing: str = ""
    full_message: str = ""
    short_message: str = ""
    warnings: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    confidence: int = 0

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, v):
        return _clamp_int(v, 0, 100)

    @field_validator("proposed_price", "proposed_delivery_days", mode="before")
    @classmethod
    def _clamp_nonnegative(cls, v):
        return _clamp_int(v, 0)

    @field_validator("portfolio_ids", mode="before")
    @classmethod
    def _coerce_ids(cls, v):
        if not v:
            return []
        result = []
        for item in v:
            try:
                result.append(int(item))
            except (TypeError, ValueError):
                continue
        return result

    @field_validator(
        "skills_to_highlight", "portfolio_reasons", "proposed_approach",
        "answers_to_client_questions", "questions_for_client", "warnings", "missing_information",
        mode="before",
    )
    @classmethod
    def _coerce_list(cls, v):
        if v is None:
            return []
        if isinstance(v, list):
            return [item if isinstance(item, str) else str(item) for item in v]
        return [str(v)]
