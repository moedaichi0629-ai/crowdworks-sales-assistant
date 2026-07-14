"""危険・低品質案件の単純キーワード一致による検出（AIの文脈判定と併用する一次判定）。"""
from __future__ import annotations

from src.config import DEFAULT_DANGER_KEYWORD_CATEGORIES

CRITICAL_CATEGORIES = {
    "初期費用・登録費用の要求", "教材・商品・サービスの購入要求", "無報酬テスト",
    "仮払い前の作業要求", "投資・副業コミュニティへの勧誘", "成人向け・ギャンブル関連",
}


def analyze_safety_rule_based(job: dict, danger_keyword_categories: dict | None = None) -> dict:
    """案件本文等を危険キーワードカテゴリと単純一致させ、安全度スコアを算出する。

    戻り値: {
        "safety_score": int, "risk_level": str,
        "detected_risks": [{"category": str, "source": "rule", "matched_keywords": [str]}],
    }
    """
    categories = danger_keyword_categories or DEFAULT_DANGER_KEYWORD_CATEGORIES
    text = " ".join(
        str(job.get(field) or "") for field in ("title", "description", "body")
    )

    detected_risks: list[dict] = []
    penalty = 0

    for category, keywords in categories.items():
        matched = [kw for kw in keywords if kw and kw in text]
        if matched:
            detected_risks.append({"category": category, "source": "rule", "matched_keywords": matched})
            penalty += 20 if category in CRITICAL_CATEGORIES else 12

    safety_score = max(0, 100 - penalty)

    if any(r["category"] in CRITICAL_CATEGORIES for r in detected_risks):
        risk_level = "critical"
    elif len(detected_risks) >= 2:
        risk_level = "high"
    elif len(detected_risks) == 1:
        risk_level = "medium"
    else:
        risk_level = "low"

    return {
        "safety_score": safety_score,
        "risk_level": risk_level,
        "detected_risks": detected_risks,
    }
