"""営業文生成の停止条件チェックと、AI出力の安全性検証・修正を行う。

危険・低品質案件では営業文を自動生成せず警告を表示し（要件15）、
AIが虚偽の実績・存在しないURL・結果保証表現などを生成した場合は
警告または機械的に修正する（要件26）。
"""
from __future__ import annotations

import re

from src.config import (
    APPLICATION_MIN_BODY_CHARS,
    APPLICATION_MIN_SAFETY_SCORE,
    APPLICATION_STOP_KEYWORD_CATEGORIES,
)

_URL_RE = re.compile(r"https?://[^\s、。「」『』()\[\]]+")

# 結果・効果を保証する表現（要件26: 「AIが以下を生成した場合は警告または修正」）
GUARANTEE_PHRASES = [
    "効果を保証", "必ず成果", "確実に売上", "採用を保証", "100%成功", "必ず集客",
    "売上を保証", "絶対に上手くいきます", "必ず上位表示", "確実に効果が出ます",
]

# 実務経験を断定する表現（未確認の場合に警告する）
REAL_JOB_CLAIM_PHRASES = ["実務で多数経験", "実務経験が豊富", "実案件で豊富な実績", "長年の実務経験"]


def _job_text(job: dict) -> str:
    return " ".join(str(job.get(field) or "") for field in ("title", "description", "body"))


def check_stop_conditions(
    job: dict,
    latest_analysis: dict | None,
    profile: dict | None = None,
    min_safety_score: int = APPLICATION_MIN_SAFETY_SCORE,
) -> dict:
    """営業文生成を停止すべきか判定する。

    戻り値: {"should_stop": bool, "reasons": [str]}
    """
    reasons: list[str] = []

    if latest_analysis:
        risk_level = latest_analysis.get("risk_level")
        safety_score = latest_analysis.get("safety_score")
        if risk_level == "critical":
            reasons.append("危険レベルが「非常に高い（critical)」と判定されているため、営業文の自動生成を停止しました。")
        if safety_score is not None and safety_score < min_safety_score:
            reasons.append(f"安全度スコア（{safety_score}点）が基準値（{min_safety_score}点）未満のため、営業文の自動生成を停止しました。")

    body = (job.get("body") or job.get("description") or "").strip()
    if len(body) < APPLICATION_MIN_BODY_CHARS:
        reasons.append("案件本文の情報がほぼ無く、内容を正しく判断できないため、営業文の自動生成を停止しました。")

    text = _job_text(job)
    for category, keywords in APPLICATION_STOP_KEYWORD_CATEGORIES.items():
        hits = [k for k in keywords if k and k in text]
        if hits:
            reasons.append(f"「{category}」に該当する可能性がある表現を検出したため、営業文の自動生成を停止しました（該当語句: {', '.join(hits[:3])}）。")

    if profile:
        excluded = (profile.get("difficult_conditions") or {}).get("excluded_conditions", [])
        hits = [c for c in excluded if c and c in text]
        if hits:
            reasons.append(f"ユーザーの対応困難条件に明確に該当するため、営業文の自動生成を停止しました（該当: {', '.join(hits[:3])}）。")

    return {"should_stop": bool(reasons), "reasons": reasons}


def _strip_disallowed_urls(text: str, allowed_urls: set[str]) -> tuple[str, list[str]]:
    warnings: list[str] = []
    if not text:
        return text, warnings

    def _replace(match: re.Match) -> str:
        url = match.group(0).rstrip(".,、。")
        if url in allowed_urls:
            return match.group(0)
        warnings.append(f"案件と無関係、または未登録のURL（{url}）を検出したため削除しました。")
        return ""

    cleaned = _URL_RE.sub(_replace, text)
    return cleaned, warnings


def validate_application_message(
    full_message: str,
    short_message: str,
    allowed_urls: set[str],
    profile_skills: list[dict] | None = None,
) -> dict:
    """AIが生成した営業文本文を検証し、危険な内容を除去・警告する。

    戻り値: {"full_message": str, "short_message": str, "warnings": [str]}
    """
    warnings: list[str] = []

    full_message, url_warnings_full = _strip_disallowed_urls(full_message or "", allowed_urls)
    short_message, url_warnings_short = _strip_disallowed_urls(short_message or "", allowed_urls)
    warnings.extend(url_warnings_full)
    warnings.extend(url_warnings_short)

    combined = f"{full_message}\n{short_message}"
    for phrase in GUARANTEE_PHRASES:
        if phrase in combined:
            warnings.append(f"結果を保証する表現（「{phrase}」）が含まれています。応募前に必ず修正してください。")

    has_real_job_experience = bool(
        profile_skills and any(s.get("experience_type") == "実案件" for s in profile_skills)
    )
    if not has_real_job_experience:
        for phrase in REAL_JOB_CLAIM_PHRASES:
            if phrase in combined:
                warnings.append(f"実務経験を断定する表現（「{phrase}」）が含まれていますが、実案件経験は未登録です。応募前に必ず修正してください。")

    return {"full_message": full_message, "short_message": short_message, "warnings": warnings}
