"""案件ごとの営業文生成オーケストレーション。

ポートフォリオ自動選択・応募金額提案・納期提案・クライアント質問抽出の結果を統合し、
AI（利用可能な場合）または テンプレート（AI APIなしの場合・AI失敗時のフォールバック）で
営業文を生成する。危険案件など生成を停止すべき場合は GenerationBlockedError を送出する。
"""
from __future__ import annotations

import sqlite3

from src.ai.base_client import AIClientError, BaseAIClient
from src.application.application_cache import compute_content_hash
from src.application.application_prompt_builder import build_system_prompt, build_user_prompt
from src.application.application_response_parser import ResponseParseError, parse_application_response
from src.application.application_validator import check_stop_conditions, validate_application_message
from src.application.client_question_extractor import extract_client_questions
from src.application.template_generator import detect_template_category, generate_from_template, recommend_tone
from src.config import (
    APPLICATION_PROMPT_VERSION,
    DEFAULT_MAX_APPLICATION_CHARS,
    LENGTH_STANDARD,
    PREP_STATUS_DRAFT,
    PREP_STATUS_NEEDS_REVIEW,
)
from src.delivery.delivery_service import suggest_delivery
from src.logger import get_logger
from src.portfolio.portfolio_service import (
    compute_and_save_portfolio_matches,
    get_selected_portfolios_with_detail,
    list_portfolio_matches,
    update_manual_portfolio_selection,
)
from src.pricing.pricing_service import suggest_price

logger = get_logger()


class GenerationBlockedError(Exception):
    """危険案件・低品質案件のため営業文生成を停止した。"""

    def __init__(self, reasons: list[str]):
        self.reasons = reasons
        super().__init__("; ".join(reasons))


def _candidate_portfolios(conn: sqlite3.Connection, job_id: int, top_n: int = 6) -> list[dict]:
    from src.repositories import get_portfolios_by_ids

    matches = list_portfolio_matches(conn, job_id)[:top_n]
    portfolio_map = {p["id"]: p for p in get_portfolios_by_ids(conn, [m["portfolio_id"] for m in matches])}
    result = []
    for m in matches:
        p = portfolio_map.get(m["portfolio_id"])
        if not p:
            continue
        result.append({**p, "relevance_score": m["relevance_score"], "match_reason": m["match_reason"]})
    return result


def _summarize_if_too_long(full_message: str, max_chars: int) -> tuple[str, bool]:
    if len(full_message) <= max_chars:
        return full_message, False
    paragraphs = [p for p in full_message.split("\n\n") if p]
    summarized = "\n\n".join(paragraphs[:1] + paragraphs[-2:]) if len(paragraphs) > 3 else full_message
    if len(summarized) > max_chars:
        summarized = summarized[:max_chars].rstrip() + "…"
    return summarized, True


def generate_application(
    conn: sqlite3.Connection,
    job: dict,
    profile_bundle: dict,
    latest_analysis: dict | None,
    ai_client: BaseAIClient | None,
    generation_type: str = "ai",
    tone: str | None = None,
    length_type: str = LENGTH_STANDARD,
    show_headings: bool = True,
    additional_message: str | None = None,
    exclude_content: str | None = None,
    manual_portfolio_ids: list[int] | None = None,
    price_override: int | None = None,
    delivery_days_override: int | None = None,
    max_chars: int = DEFAULT_MAX_APPLICATION_CHARS,
    prompt_version: str = APPLICATION_PROMPT_VERSION,
    max_tokens: int = 1500,
) -> dict:
    """1案件について営業文を生成する。危険案件の場合は GenerationBlockedError を送出する。"""
    profile = profile_bundle["profile"]
    skills = profile_bundle["skills"]

    stop_check = check_stop_conditions(job, latest_analysis, profile)
    if stop_check["should_stop"]:
        logger.warning("営業文生成を停止しました: job_id=%s reasons=%s", job["id"], stop_check["reasons"])
        raise GenerationBlockedError(stop_check["reasons"])

    compute_and_save_portfolio_matches(conn, job, profile["id"])
    if manual_portfolio_ids is not None:
        update_manual_portfolio_selection(conn, job["id"], manual_portfolio_ids)

    candidates = _candidate_portfolios(conn, job["id"])
    selected_portfolios = get_selected_portfolios_with_detail(conn, job["id"])

    category = detect_template_category(job)
    tone = tone or recommend_tone(category)

    hours_min = (latest_analysis or {}).get("estimated_hours_min")
    hours_max = (latest_analysis or {}).get("estimated_hours_max")
    est_days = (latest_analysis or {}).get("estimated_days")
    difficulty = (latest_analysis or {}).get("difficulty")

    price_info = suggest_price(conn, job, hours_min, hours_max, difficulty)
    if price_override is not None:
        price_info = {**price_info, "proposed_price": price_override, "price_reason": "ユーザー指定金額を使用", "is_uncertain": False}

    delivery_info = suggest_delivery(
        conn, job, hours_min, hours_max, est_days, difficulty, profile.get("daily_available_hours"),
    )
    if delivery_days_override is not None:
        delivery_info = {
            **delivery_info, "recommended_delivery_days": delivery_days_override,
            "delivery_reason": "ユーザー指定納期を使用",
        }

    client_questions = extract_client_questions(job)

    provider = ai_client.provider_name if ai_client and generation_type == "ai" else "template"
    model = ai_client.model if ai_client and generation_type == "ai" else None

    used_ai = False
    analysis_error = None
    template_result = None

    if ai_client is not None and generation_type == "ai":
        try:
            system_prompt = build_system_prompt()
            user_prompt = build_user_prompt(
                job, profile, skills, candidates, latest_analysis, price_info, delivery_info,
                client_questions, tone, length_type, show_headings, additional_message, exclude_content,
            )
            response = ai_client.complete(system_prompt, user_prompt, max_tokens=max_tokens)
            try:
                parsed = parse_application_response(response.text)
            except ResponseParseError as exc:
                logger.warning("営業文AI応答のJSON解析に失敗しました。1回だけ再試行します: job_id=%s error=%s", job["id"], exc)
                retry_prompt = user_prompt + "\n\n※前回の応答はJSON形式として不正でした。必ず有効なJSONのみを出力してください。"
                response2 = ai_client.complete(system_prompt, retry_prompt, max_tokens=max_tokens)
                parsed = parse_application_response(response2.text)

            candidate_ids = {c["id"] for c in candidates}
            chosen_ids = [pid for pid in parsed.portfolio_ids if pid in candidate_ids] or [
                p["id"] for p in selected_portfolios
            ]
            if set(chosen_ids) != {p["id"] for p in selected_portfolios}:
                update_manual_portfolio_selection(conn, job["id"], chosen_ids)
                selected_portfolios = get_selected_portfolios_with_detail(conn, job["id"])

            allowed_urls = {
                p.get("portfolio_url") for p in candidates if p.get("portfolio_url")
            } | {p.get("github_url") for p in candidates if p.get("github_url")}
            validated = validate_application_message(
                parsed.full_message, parsed.short_message, allowed_urls, skills,
            )

            result = {
                "application_title": parsed.application_title or f"{job.get('title') or ''} への応募",
                "opening": parsed.opening, "understanding": parsed.understanding,
                "matching_reason": parsed.matching_reason,
                "skills_to_highlight": parsed.skills_to_highlight,
                "portfolio_ids": chosen_ids, "portfolio_reasons": parsed.portfolio_reasons,
                "proposed_approach": parsed.proposed_approach,
                "proposed_price": parsed.proposed_price or price_info.get("proposed_price"),
                "price_reason": parsed.price_reason or price_info.get("price_reason", ""),
                "proposed_delivery_days": parsed.proposed_delivery_days or delivery_info.get("recommended_delivery_days"),
                "delivery_reason": parsed.delivery_reason or delivery_info.get("delivery_reason", ""),
                "answers_to_client_questions": parsed.answers_to_client_questions,
                "questions_for_client": parsed.questions_for_client or delivery_info.get("pre_confirmation_items", []),
                "closing": parsed.closing,
                "full_message": validated["full_message"],
                "short_message": validated["short_message"],
                "warnings": list(parsed.warnings) + validated["warnings"] + list(delivery_info.get("warnings") or []),
                "missing_information": parsed.missing_information,
                "confidence_score": parsed.confidence,
            }
            used_ai = True
        except (AIClientError, ResponseParseError) as exc:
            analysis_error = f"AI営業文生成に失敗したため、テンプレートで下書きを作成しました: {exc}"
            logger.error("営業文AI生成失敗: job_id=%s error=%s", job["id"], exc)

    if not used_ai:
        template_result = generate_from_template(
            job, profile, skills, selected_portfolios, price_info, delivery_info, client_questions,
            tone, length_type, additional_message, exclude_content,
        )
        result = {k: v for k, v in template_result.items() if k not in ("generation_type", "category")}
        provider = "template"
        model = None

    full_message, was_summarized = _summarize_if_too_long(result["full_message"], max_chars)
    if was_summarized:
        result["full_message"] = full_message
        result.setdefault("warnings", [])
        result["warnings"].append(f"文字数が上限（{max_chars}文字）を超えたため、要約版を作成しました。内容をご確認ください。")

    char_count = len(result["full_message"])

    content_hash = compute_content_hash(
        job, latest_analysis, profile.get("updated_at"), profile.get("version"),
        result.get("portfolio_ids", []), "ai" if used_ai else "template", tone, length_type,
        result.get("proposed_price"), result.get("proposed_delivery_days"), additional_message,
        exclude_content, prompt_version, provider, model,
    )

    preparation_status = PREP_STATUS_NEEDS_REVIEW if result.get("warnings") else PREP_STATUS_DRAFT

    result.update({
        "generation_type": "ai" if used_ai else ("template_fallback" if analysis_error else "template"),
        "tone": tone,
        "length_type": length_type,
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "source_hash": content_hash,
        "preparation_status": preparation_status,
        "char_count": char_count,
        "analysis_error": analysis_error,
        "client_questions": client_questions,
        "candidate_portfolios": candidates,
    })
    return result
