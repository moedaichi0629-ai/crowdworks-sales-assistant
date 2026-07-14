"""AI APIが利用できない場合でも、案件情報とプロフィールから営業文の下書きを作成する。

案件カテゴリを判定してテンプレートカテゴリに割り当て、登録済みの制作実績・
スキル・料金/納期提案・抽出済みクライアント質問を組み合わせて文章を組み立てる。
虚偽の実績や結果保証の表現は生成しない。
"""
from __future__ import annotations

from src.config import (
    LENGTH_CHAR_RANGES,
    LENGTH_DETAILED,
    LENGTH_SHORT,
    LENGTH_STANDARD,
    TONE_ACHIEVEMENT,
    TONE_AI_DESIGN,
    TONE_AI_DEV,
    TONE_AUTOMATION,
    TONE_BANNER,
    TONE_DATA_ENTRY,
    TONE_DESIGN,
    TONE_ENTHUSIASTIC,
    TONE_LOGO_PRINT,
    TONE_POLITE,
    TONE_PROPOSAL,
    TONE_SHORT,
    TONE_SINCERE_BEGINNER,
    TONE_SNS_DESIGN,
    TONE_STANDARD,
    TONE_TECHNICAL,
    TONE_WEBSITE,
)
from src.portfolio.portfolio_category_classifier import classify_job_category

TEMPLATE_CATEGORIES = [
    "AI開発", "API連携", "業務自動化", "ホームページ制作", "LP制作", "Webアプリ", "チャットボット",
    "データ入力", "リサーチ", "SNS運用", "バナー制作", "SNS投稿画像制作", "YouTubeサムネイル制作",
    "ロゴ制作", "名刺・ショップカード制作", "チラシ・販促物制作", "Webデザイン", "資料・スライドデザイン",
    "AI×デザイン", "その他",
]

# 具体的なカテゴリから優先的に判定する（順序が判定優先度）
_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "バナー制作": ["バナー制作", "バナー"],
    "SNS投稿画像制作": ["SNS投稿画像", "Instagram投稿画像", "インスタ投稿"],
    "YouTubeサムネイル制作": ["YouTubeサムネイル", "サムネイル制作", "サムネ"],
    "ロゴ制作": ["ロゴ制作", "ロゴデザイン"],
    "名刺・ショップカード制作": ["名刺", "ショップカード"],
    "チラシ・販促物制作": ["チラシ", "販促物", "フライヤー"],
    "資料・スライドデザイン": ["資料デザイン", "スライドデザイン", "プレゼン資料"],
    "Webデザイン": ["Webデザイン", "サイトデザイン"],
    "チャットボット": ["チャットボット", "Bot開発", "AIチャットボット"],
    "LP制作": ["LP制作", "LPデザイン", "ランディングページ"],
    "ホームページ制作": ["ホームページ制作", "ホームページ", "コーポレートサイト"],
    "Webアプリ": ["Webアプリ", "Webシステム", "アプリ開発"],
    "API連携": ["API連携", "外部API", "Webhook"],
    "業務自動化": ["業務自動化", "自動化", "GAS", "Google Apps Script", "定期実行"],
    "AI開発": ["AI開発", "ChatGPT", "OpenAI", "Claude", "Gemini", "Dify", "生成AI"],
    "データ入力": ["データ入力", "入力作業"],
    "リサーチ": ["リサーチ", "調査", "情報収集"],
    "SNS運用": ["SNS運用", "SNS投稿代行", "SNSアカウント運用"],
}

_CATEGORY_RECOMMENDED_TONE: dict[str, str] = {
    "バナー制作": TONE_BANNER, "SNS投稿画像制作": TONE_SNS_DESIGN, "YouTubeサムネイル制作": TONE_BANNER,
    "ロゴ制作": TONE_LOGO_PRINT, "名刺・ショップカード制作": TONE_LOGO_PRINT, "チラシ・販促物制作": TONE_LOGO_PRINT,
    "資料・スライドデザイン": TONE_DESIGN, "Webデザイン": TONE_DESIGN, "チャットボット": TONE_AI_DEV,
    "LP制作": TONE_WEBSITE, "ホームページ制作": TONE_WEBSITE, "Webアプリ": TONE_AI_DEV,
    "API連携": TONE_AI_DEV, "業務自動化": TONE_AUTOMATION, "AI開発": TONE_AI_DEV,
    "データ入力": TONE_DATA_ENTRY, "リサーチ": TONE_DATA_ENTRY, "SNS運用": TONE_SNS_DESIGN,
    "AI×デザイン": TONE_AI_DESIGN, "その他": TONE_STANDARD,
}

_OPENING_TEXT: dict[str, str] = {
    "AI開発": "AI開発の案件を拝見し、これまでの個人開発経験を活かせると考え応募いたしました。",
    "API連携": "API連携を伴う案件を拝見し、外部サービス連携の実装経験を活かせると考え応募いたしました。",
    "業務自動化": "業務自動化に関する案件を拝見し、効率化のお手伝いができればと思い応募いたしました。",
    "ホームページ制作": "ホームページ制作の案件を拝見し、貴社のご要望に沿ったサイト制作ができればと考え応募いたしました。",
    "LP制作": "LP制作の案件を拝見し、目的に沿ったランディングページ制作のお力になれればと考え応募いたしました。",
    "Webアプリ": "Webアプリ開発の案件を拝見し、これまでの制作経験を活かせると考え応募いたしました。",
    "チャットボット": "AIチャットボット開発の案件を拝見し、個人開発の経験を活かせると考え応募いたしました。",
    "データ入力": "データ入力・リサーチ業務の案件を拝見し、丁寧かつ正確に対応できればと考え応募いたしました。",
    "リサーチ": "リサーチ業務の案件を拝見し、情報整理のお手伝いができればと考え応募いたしました。",
    "SNS運用": "SNS運用・投稿画像制作の案件を拝見し、お力になれればと考え応募いたしました。",
    "バナー制作": "バナー制作の案件を拝見し、デザイン制作の経験を活かせると考え応募いたしました。",
    "SNS投稿画像制作": "SNS投稿画像制作の案件を拝見し、デザイン制作の経験を活かせると考え応募いたしました。",
    "YouTubeサムネイル制作": "YouTubeサムネイル制作の案件を拝見し、視認性を意識した制作でお力になれればと考え応募いたしました。",
    "ロゴ制作": "ロゴ制作の案件を拝見し、貴社のイメージに合うデザインをご提案できればと考え応募いたしました。",
    "名刺・ショップカード制作": "名刺・ショップカード制作の案件を拝見し、お力になれればと考え応募いたしました。",
    "チラシ・販促物制作": "チラシ・販促物制作の案件を拝見し、情報が伝わりやすいデザインをご提案できればと考え応募いたしました。",
    "Webデザイン": "Webデザインの案件を拝見し、デザイン制作の経験を活かせると考え応募いたしました。",
    "資料・スライドデザイン": "資料・スライドデザインの案件を拝見し、見やすく伝わりやすい資料制作でお力になれればと考え応募いたしました。",
    "AI×デザイン": "AIとデザインの両方が関わる案件を拝見し、両方の制作経験を活かせると考え応募いたしました。",
    "その他": "貴社の案件を拝見し、お力になれればと考え応募いたしました。",
}

_TONE_CLOSING: dict[str, str] = {
    TONE_POLITE: "ご検討のほど、何卒よろしくお願いいたします。",
    TONE_ENTHUSIASTIC: "ぜひこの案件に携わらせていただきたく、精一杯対応させていただきます。よろしくお願いいたします。",
    TONE_SINCERE_BEGINNER: "実務経験を増やしている段階ではございますが、誠実に丁寧に対応させていただきます。よろしくお願いいたします。",
    TONE_ACHIEVEMENT: "これまでの制作実績を踏まえ、しっかりと対応させていただきます。よろしくお願いいたします。",
    TONE_PROPOSAL: "進め方についてもご相談しながら、より良い形でご提案できればと思います。よろしくお願いいたします。",
    TONE_TECHNICAL: "技術面でご不明点があれば遠慮なくご質問ください。よろしくお願いいたします。",
    TONE_SHORT: "よろしくお願いいたします。",
}
_DEFAULT_CLOSING = "ご検討いただけますと幸いです。よろしくお願いいたします。"


def detect_template_category(job: dict) -> str:
    """案件本文からもっとも近いテンプレートカテゴリを判定する。"""
    text = " ".join(str(job.get(f) or "") for f in ("title", "category", "description", "body"))

    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            classification = classify_job_category(job)
            if classification["is_ai_design"] and classification["is_design"] and classification["is_development"]:
                return "AI×デザイン"
            return category

    classification = classify_job_category(job)
    if classification["is_ai_design"]:
        return "AI×デザイン"
    if classification["is_design"]:
        return "Webデザイン"
    if classification["is_development"]:
        return "AI開発"
    return "その他"


def recommend_tone(category: str) -> str:
    return _CATEGORY_RECOMMENDED_TONE.get(category, TONE_STANDARD)


def _matched_skills_text(job: dict, skills: list[dict]) -> list[str]:
    text = " ".join(str(job.get(f) or "") for f in ("title", "description", "body")).lower()
    return [s["skill_name"] for s in skills if s.get("skill_name") and s["skill_name"].lower() in text]


def _portfolio_section(selected_portfolios: list[dict]) -> tuple[str, list[str]]:
    if not selected_portfolios:
        return "関連する制作実績: 関連実績なし（本案件に直接一致する制作実績は登録されていません）", []
    lines = []
    reasons = []
    for p in selected_portfolios:
        url = p.get("portfolio_url") or p.get("github_url")
        desc = p.get("sales_description") or p.get("description") or ""
        line = f"「{p['title']}」{desc}"
        if url:
            line += f"（{url}）"
        lines.append(line)
        reasons.append(p.get("match_reason") or "")
    return "関連する制作実績:\n" + "\n".join(f"・{l}" for l in lines), reasons


def _experience_phrase(skills: list[dict], matched: list[str]) -> str:
    matched_skill_objs = [s for s in skills if s.get("skill_name") in matched]
    if any(s.get("experience_type") == "実案件" for s in matched_skill_objs):
        return "実案件での対応経験があります。"
    if any(s.get("experience_type") == "公開実績" for s in matched_skill_objs):
        return "個人開発・公開実績として制作した経験があります。"
    if matched_skill_objs:
        return "個人開発・学習を通して使用した経験があります。"
    return "学習を通して知識があり、対応可能です。"


def generate_from_template(
    job: dict,
    profile: dict,
    skills: list[dict],
    selected_portfolios: list[dict],
    price_info: dict,
    delivery_info: dict,
    client_questions: list[dict],
    tone: str | None = None,
    length_type: str = LENGTH_STANDARD,
    additional_message: str | None = None,
    exclude_content: str | None = None,
) -> dict:
    """AI APIを使わずに、ルールベース＋テンプレートで営業文の下書きを作成する。"""
    category = detect_template_category(job)
    tone = tone or recommend_tone(category)

    matched_skills = _matched_skills_text(job, skills)
    opening = _OPENING_TEXT.get(category, _OPENING_TEXT["その他"])

    client_needs_text = "ご依頼内容を拝見し、必要な対応内容を確認いたしました。"
    understanding = client_needs_text

    matching_reason = (
        f"{'、'.join(matched_skills[:5]) if matched_skills else '関連する基礎知識'}を活かして対応できると考えております。"
        + _experience_phrase(skills, matched_skills)
    )

    portfolio_text, portfolio_reasons = _portfolio_section(selected_portfolios)

    approach_lines = ["ご要望をヒアリングし、進め方をすり合わせたうえで着手いたします。"]
    if length_type in (LENGTH_STANDARD, LENGTH_DETAILED):
        approach_lines.append("作業途中で認識齟齬が出ないよう、適宜進捗をご共有いたします。")
    if length_type == LENGTH_DETAILED:
        approach_lines.append("納品後の修正対応についても、事前にすり合わせのうえ対応いたします。")

    price_text = f"ご提案金額: {price_info.get('proposed_price')}円（{price_info.get('price_reason', '')}）"
    delivery_text = f"ご提案納期: 約{delivery_info.get('recommended_delivery_days')}日（{delivery_info.get('delivery_reason', '')}）"

    answers_to_client_questions = []
    for q in client_questions:
        category_ans = q.get("answer_category")
        answer = _experience_phrase(skills, matched_skills)
        if category_ans == "design":
            design_pf = next((p for p in selected_portfolios if p.get("portfolio_type") == "design"), None)
            if design_pf and design_pf.get("portfolio_url"):
                answer += f" デザイン実績: {design_pf['portfolio_url']}"
        elif category_ans == "github":
            gh_pf = next((p for p in selected_portfolios if p.get("github_url")), None)
            if gh_pf and gh_pf.get("github_url"):
                answer += f" GitHub: {gh_pf['github_url']}"
        elif category_ans == "ai_dev":
            dev_pf = next((p for p in selected_portfolios if p.get("portfolio_type") == "development"), None)
            if dev_pf and dev_pf.get("portfolio_url"):
                answer += f" 実績ポートフォリオ: {dev_pf['portfolio_url']}"
        answers_to_client_questions.append({"question": q["question"], "answer": answer})

    questions_for_client: list[str] = list(delivery_info.get("pre_confirmation_items") or [])

    closing = _TONE_CLOSING.get(tone, _DEFAULT_CLOSING)

    sections = [opening, understanding, matching_reason, portfolio_text]
    sections.append("進め方: " + " ".join(approach_lines))
    sections.append(delivery_text)
    sections.append(price_text)
    if answers_to_client_questions:
        sections.append(
            "ご質問への回答:\n" + "\n".join(f"・{a['question']} → {a['answer']}" for a in answers_to_client_questions)
        )
    if questions_for_client:
        sections.append("事前に確認させていただきたい内容:\n" + "\n".join(f"・{q}" for q in questions_for_client))
    if additional_message:
        sections.append(additional_message)
    sections.append(closing)

    full_message = "\n\n".join(s for s in sections if s)

    if exclude_content:
        full_message = full_message.replace(exclude_content, "")

    short_sections = [opening, matching_reason, price_text, delivery_text, closing]
    short_message = "\n\n".join(s for s in short_sections if s)

    warnings: list[str] = list(delivery_info.get("warnings") or [])
    if price_info.get("is_uncertain"):
        warnings.append("作業内容が確定していないため、提示金額は目安です。応募後にすり合わせてください。")

    return {
        "application_title": f"【{category}】{job.get('title') or ''} への応募",
        "opening": opening,
        "understanding": understanding,
        "matching_reason": matching_reason,
        "skills_to_highlight": matched_skills,
        "portfolio_ids": [p["id"] for p in selected_portfolios],
        "portfolio_reasons": portfolio_reasons,
        "proposed_approach": approach_lines,
        "proposed_price": price_info.get("proposed_price"),
        "price_reason": price_info.get("price_reason", ""),
        "proposed_delivery_days": delivery_info.get("recommended_delivery_days"),
        "delivery_reason": delivery_info.get("delivery_reason", ""),
        "answers_to_client_questions": answers_to_client_questions,
        "questions_for_client": questions_for_client,
        "closing": closing,
        "full_message": full_message,
        "short_message": short_message,
        "warnings": warnings,
        "missing_information": [],
        "confidence": 50,
        "generation_type": "template",
        "tone": tone,
        "length_type": length_type,
        "category": category,
    }


def _template_body_for_category(category: str) -> str:
    return _OPENING_TEXT.get(category, _OPENING_TEXT["その他"])


DEFAULT_TEMPLATE_DEFINITIONS: list[dict] = [
    {
        "template_name": f"{category}テンプレート",
        "category": category,
        "tone": recommend_tone(category),
        "length_type": LENGTH_STANDARD,
        "template_body": _template_body_for_category(category),
    }
    for category in TEMPLATE_CATEGORIES
]
