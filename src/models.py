"""案件データの型定義。"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from src.config import STATUS_UNCONFIRMED


class Job(BaseModel):
    """1件の案件情報を表すモデル。取得できなかった項目はNoneのまま保存する。"""

    id: Optional[int] = None
    external_job_id: Optional[str] = None
    title: str
    url: Optional[str] = None
    normalized_url: Optional[str] = None
    description: Optional[str] = None
    body: Optional[str] = None
    job_type: Optional[str] = None
    category: Optional[str] = None
    budget_min: Optional[int] = None
    budget_max: Optional[int] = None
    budget_text: Optional[str] = None
    hourly_rate: Optional[str] = None
    published_at: Optional[str] = None
    deadline: Optional[str] = None
    applicant_count: Optional[int] = None
    recruitment_count: Optional[int] = None
    client_name: Optional[str] = None
    client_rating: Optional[float] = None
    client_review_count: Optional[int] = None
    identity_verified: Optional[bool] = None
    rule_check_verified: Optional[bool] = None
    matched_keyword: Optional[str] = None
    excluded_keyword: Optional[str] = None
    source_type: Optional[str] = None
    status: str = STATUS_UNCONFIRMED
    is_favorite: bool = False
    memo: Optional[str] = None
    collected_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
