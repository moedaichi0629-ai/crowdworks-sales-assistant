"""統計結果からルールベースで改善候補（気づき）を生成する。

因果関係は断定せず、常に「傾向」として表現する。母数が少ない場合は明記し、
データが無い項目については推測で文章を作らない。
"""
from __future__ import annotations

import sqlite3

from src.analytics.category_analytics import analyze_by_category_group
from src.analytics.kpi_service import get_base_records
from src.analytics.message_analytics import LOW_SAMPLE_THRESHOLD, analyze_by_tone
from src.analytics.portfolio_analytics import analyze_by_portfolio
from src.analytics.timing_analytics import analyze_by_freshness
from src.config import CATEGORY_GROUP_AI_DEV, CATEGORY_GROUP_DESIGN

CAUTION_THRESHOLD = 10


def _hedge_suffix(count: int) -> str:
    if count < LOW_SAMPLE_THRESHOLD:
        return f"（応募{count}件のため参考値です）"
    if count < CAUTION_THRESHOLD:
        return f"（応募{count}件とまだ少ないため、参考程度にご覧ください）"
    return ""


def generate_insights(conn: sqlite3.Connection, date_from: str, date_to: str) -> list[str]:
    """指定期間のデータから、日本語の気づき文を最大10件程度生成する。"""
    records = get_base_records(conn, date_from, date_to)
    insights: list[str] = []

    if not records:
        return insights

    # --- ジャンル比較(AI・開発 vs デザイン) ---
    by_group = analyze_by_category_group(records)
    ai_dev = by_group.get(CATEGORY_GROUP_AI_DEV, {})
    design = by_group.get(CATEGORY_GROUP_DESIGN, {})
    ai_rate, design_rate = ai_dev.get("response_rate"), design.get("response_rate")
    ai_count, design_count = ai_dev.get("application_count", 0), design.get("application_count", 0)
    if ai_rate is not None and design_rate is not None and ai_count and design_count:
        diff = round(ai_rate - design_rate, 1)
        if abs(diff) >= 1:
            higher, lower, higher_rate_diff = (
                ("AI・開発案件", "デザイン案件", diff) if diff > 0 else ("デザイン案件", "AI・開発案件", -diff)
            )
            min_count = min(ai_count, design_count)
            insights.append(
                f"・{higher}は{lower}より返信率が{higher_rate_diff:.0f}ポイント高い傾向です。{_hedge_suffix(min_count)}"
            )

    # --- 掲載からの経過時間別の傾向 ---
    freshness = analyze_by_freshness(records)
    within_24h = freshness.get("24時間以内", {})
    others_count = sum(
        (freshness.get(k, {}).get("application_count") or 0) for k in ("48時間以内", "72時間以降")
    )
    others_responded = sum(
        round((freshness.get(k, {}).get("response_rate") or 0) * (freshness.get(k, {}).get("application_count") or 0) / 100)
        for k in ("48時間以内", "72時間以降")
    )
    if within_24h.get("application_count") and others_count:
        others_rate = round(others_responded / others_count * 100, 1)
        if (within_24h.get("response_rate") or 0) > others_rate:
            insights.append(
                f"・掲載24時間以内に応募した案件の返信率が高い傾向です。"
                f"{_hedge_suffix(within_24h.get('application_count', 0))}"
            )

    # --- 営業文タイプ別 ---
    by_tone = analyze_by_tone(records)
    for tone, stats in by_tone.items():
        if stats.get("is_reference_only"):
            insights.append(f"・{tone}型は応募数が{stats['usage_count']}件のため、まだ判断材料が不足しています。")
        elif stats.get("response_rate") is not None:
            insights.append(
                f"・{tone}型の返信率は{stats['response_rate']:.0f}%です。{_hedge_suffix(stats['usage_count'])}"
            )

    # --- ポートフォリオ別 ---
    by_portfolio = analyze_by_portfolio(conn, records)
    for title, stats in by_portfolio.items():
        if stats.get("response_rate") is None:
            continue
        insights.append(
            f"・「{title}」を使用した応募の返信率は{stats['response_rate']:.0f}%です。{_hedge_suffix(stats['usage_count'])}"
        )

    return insights[:15]
