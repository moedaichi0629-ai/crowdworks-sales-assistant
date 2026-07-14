"""単体案件のAI分析オーケストレーション（ルールベース判定 + 安全性判定 + AI分析 + 総合スコア）。

AI APIが利用できない場合でも、ルールベース判定のみでフォールバック結果を返す
（「AI APIを使用できない場合の代替判定」に対応）。
"""
from __future__ import annotations

import sqlite3

from src.ai.base_client import AIClientError, BaseAIClient
from src.ai.prompt_builder import build_system_prompt, build_user_prompt
from src.ai.response_parser import ResponseParseError, parse_ai_response
from src.analysis.analysis_cache import compute_content_hash, get_cached_analysis
from src.analysis.rule_based_analyzer import analyze_rule_based, days_until_deadline
from src.analysis.safety_analyzer import analyze_safety_rule_based
from src.analysis.score_calculator import compute_priority, compute_total_score
from src.config import PROMPT_VERSION
from src.logger import get_logger

logger = get_logger()

_RISK_LEVEL_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _more_severe_risk(a: str, b: str) -> str:
    return a if _RISK_LEVEL_ORDER.get(a, 0) >= _RISK_LEVEL_ORDER.get(b, 0) else b


def _fallback_recommendation(rule_score: int) -> str:
    if rule_score >= 80:
        return "strong_apply"
    if rule_score >= 65:
        return "apply"
    if rule_score >= 45:
        return "consider"
    return "skip"


def analyze_job(
    conn: sqlite3.Connection,
    job: dict,
    profile_bundle: dict,
    analysis_settings: dict,
    ai_client: BaseAIClient | None,
    exclude_keywords: list[str] | None = None,
    force_reanalyze: bool = False,
    rule_only: bool = False,
) -> dict:
    """1案件を分析し、job_analyses へ保存可能な結果辞書を返す。

    `exclude_keywords` は案件収集設定（settingsテーブル）の除外キーワード一覧。
    戻り値には内部フラグ `_from_cache`（キャッシュ利用有無）を含む。
    """
    profile = profile_bundle["profile"]
    skills = profile_bundle["skills"]
    portfolios = profile_bundle["portfolios"]
    difficult_conditions = (profile.get("difficult_conditions") or {}).get("difficult_conditions", [])
    exclude_keywords = exclude_keywords or []

    rule_result = analyze_rule_based(
        job, skills, portfolios, difficult_conditions, exclude_keywords,
        weights=analysis_settings.get("rule_weights"),
    )
    safety_rule = analyze_safety_rule_based(job, analysis_settings.get("danger_keyword_categories"))

    provider = ai_client.provider_name if ai_client and not rule_only else "rule_only"
    model = ai_client.model if ai_client and not rule_only else None

    content_hash = compute_content_hash(job, profile.get("updated_at"), PROMPT_VERSION, provider, model)

    if not force_reanalyze:
        cached = get_cached_analysis(conn, job["id"], content_hash)
        if cached is not None:
            logger.info("キャッシュを利用しました: job_id=%s", job["id"])
            cached["_from_cache"] = True
            return cached

    min_body_chars = analysis_settings.get("min_body_chars_for_analysis", 20)
    body_len = len((job.get("body") or job.get("description") or "").strip())
    use_ai = bool(ai_client) and not rule_only and body_len >= min_body_chars

    ai_parsed = None
    analysis_error = None
    token_usage = None

    if use_ai:
        try:
            system_prompt = build_system_prompt()
            user_prompt = build_user_prompt(
                job, profile, skills, portfolios, rule_result,
                [r["category"] for r in safety_rule["detected_risks"]],
            )
            max_tokens = analysis_settings.get("max_tokens", 1500)

            logger.info("AI分析を開始します: job_id=%s provider=%s model=%s", job["id"], provider, model)
            response = ai_client.complete(system_prompt, user_prompt, max_tokens=max_tokens)
            token_usage = response.usage

            try:
                ai_parsed = parse_ai_response(response.text)
            except ResponseParseError as exc:
                logger.warning("AI応答のJSON解析に失敗しました。1回だけ再試行します: job_id=%s error=%s", job["id"], exc)
                retry_prompt = user_prompt + "\n\n※前回の応答はJSON形式として不正でした。必ず有効なJSONのみを出力してください。"
                response2 = ai_client.complete(system_prompt, retry_prompt, max_tokens=max_tokens)
                token_usage = response2.usage or token_usage
                ai_parsed = parse_ai_response(response2.text)

            logger.info("AI分析が完了しました: job_id=%s", job["id"])
        except ResponseParseError as exc:
            analysis_error = f"AI応答のJSON解析に失敗したため、ルールベース結果を使用しました: {exc}"
            logger.error("AI分析失敗(JSON解析エラー): job_id=%s error=%s", job["id"], exc)
            ai_parsed = None
        except AIClientError as exc:
            analysis_error = f"AI APIの呼び出しに失敗したため、ルールベース結果を使用しました: {exc}"
            logger.error("AI分析失敗(APIエラー): job_id=%s error=%s", job["id"], exc)
            ai_parsed = None

    days_left = days_until_deadline(job.get("deadline"))
    matched_portfolio_titles = rule_result["matched_portfolio_titles"]

    if ai_parsed is not None:
        ai_suitability_score = ai_parsed.suitability_score
        safety_score = min(safety_rule["safety_score"], ai_parsed.safety_score)
        risk_level = _more_severe_risk(safety_rule["risk_level"], ai_parsed.risk_level)
        detected_risks = list(safety_rule["detected_risks"]) + [
            {"category": r, "source": "ai"} for r in ai_parsed.detected_risks
        ]
        result = {
            "rule_based_score": rule_result["score"],
            "rule_based_breakdown": rule_result["breakdown"],
            "ai_suitability_score": ai_suitability_score,
            "recommendation": ai_parsed.recommendation,
            "difficulty": ai_parsed.difficulty,
            "confidence_score": ai_parsed.confidence,
            "summary": ai_parsed.summary,
            "client_needs": ai_parsed.client_needs,
            "required_skills": ai_parsed.required_skills,
            "matched_skills": ai_parsed.matched_skills or rule_result["matched_skills"],
            "missing_skills": ai_parsed.missing_skills,
            "matched_portfolio": ai_parsed.matched_portfolio or matched_portfolio_titles,
            "estimated_hours_min": ai_parsed.estimated_hours_min,
            "estimated_hours_max": ai_parsed.estimated_hours_max,
            "estimated_days": ai_parsed.estimated_days,
            "budget_evaluation": ai_parsed.budget_evaluation,
            "strengths": ai_parsed.strengths,
            "concerns": ai_parsed.concerns,
            "questions": ai_parsed.questions_before_applying,
            "application_strategy": ai_parsed.application_strategy,
            "analysis_reason": ai_parsed.analysis_reason,
            "safety_score": safety_score,
            "risk_level": risk_level,
            "detected_risks": detected_risks,
            "risk_reasons": ai_parsed.risk_reasons,
            "recommended_action": ai_parsed.recommended_action,
            "safety_summary": ai_parsed.safety_summary,
            "provider": provider,
            "model": model,
            "used_ai": 1,
            "token_usage": token_usage,
            "analysis_error": None,
        }
    else:
        ai_suitability_score = None
        safety_score = safety_rule["safety_score"]
        risk_level = safety_rule["risk_level"]
        result = {
            "rule_based_score": rule_result["score"],
            "rule_based_breakdown": rule_result["breakdown"],
            "ai_suitability_score": None,
            "recommendation": _fallback_recommendation(rule_result["score"]),
            "difficulty": "intermediate",
            "confidence_score": 0,
            "summary": "AI分析は利用されていないため、ルールベース判定結果のみを表示しています。",
            "client_needs": [],
            "required_skills": [],
            "matched_skills": rule_result["matched_skills"],
            "missing_skills": [],
            "matched_portfolio": matched_portfolio_titles,
            "estimated_hours_min": None,
            "estimated_hours_max": None,
            "estimated_days": None,
            "budget_evaluation": "unknown",
            "strengths": [],
            "concerns": [],
            "questions": [],
            "application_strategy": "",
            "analysis_reason": "ルールベース判定: " + " / ".join(rule_result["breakdown_labels"]),
            "safety_score": safety_score,
            "risk_level": risk_level,
            "detected_risks": safety_rule["detected_risks"],
            "risk_reasons": [],
            "recommended_action": "review" if risk_level in ("high", "critical") else "proceed",
            "safety_summary": "AIによる文脈判定は行われていません（キーワード一致のみ）。",
            "provider": provider,
            "model": model,
            "used_ai": 0,
            "token_usage": None,
            "analysis_error": analysis_error,
        }

    total_score = compute_total_score(
        ai_suitability_score, rule_result["score"], safety_score, result["budget_evaluation"],
        days_left, job.get("applicant_count"), job.get("client_rating"), job.get("identity_verified"),
        len(result["matched_portfolio"]), weights=analysis_settings.get("score_weights"),
    )
    application_priority = compute_priority(total_score, risk_level, analysis_settings.get("priority_thresholds"))

    result.update({
        "total_score": total_score,
        "application_priority": application_priority,
        "content_hash": content_hash,
        "prompt_version": PROMPT_VERSION,
        "_from_cache": False,
    })
    return result
