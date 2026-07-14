"""営業文生成AI用のプロンプトを組み立てる。"""
from __future__ import annotations

from src.config import AI_MAX_BODY_CHARS, LENGTH_CHAR_RANGES, LENGTH_MATCH_JOB
from src.utils import truncate

RESPONSE_JSON_SCHEMA_TEXT = """
{
  "application_title": "",
  "opening": "",
  "understanding": "",
  "matching_reason": "",
  "skills_to_highlight": [],
  "portfolio_ids": [],
  "portfolio_reasons": [],
  "proposed_approach": [],
  "proposed_price": 0,
  "price_reason": "",
  "proposed_delivery_days": 0,
  "delivery_reason": "",
  "answers_to_client_questions": [],
  "questions_for_client": [],
  "closing": "",
  "full_message": "",
  "short_message": "",
  "warnings": [],
  "missing_information": [],
  "confidence": 0
}
""".strip()


def build_system_prompt() -> str:
    return (
        "あなたはクラウドソーシングの応募文（営業文）作成を支援する、経験豊富な受注アドバイザーです。"
        "与えられた案件情報・AI分析結果・ユーザーのスキルプロフィール・登録済み制作実績をもとに、"
        "この案件専用の営業文を作成してください。\n\n"
        "厳守事項:\n"
        "- 必ず指定されたJSON形式のみで回答してください。JSON以外の説明文は一切含めないでください。\n"
        "- ユーザーの実績を過大評価しないでください。スキルの経験区分（学習経験・個人開発経験・"
        "公開実績・実案件経験・未確認）を区別し、実務経験が確認できないスキルを『実務経験あり』『実務で多数経験』と"
        "断定しないでください。未経験の内容を経験済みと書かないでください。\n"
        "- 提示された制作実績（portfolio候補）以外の実績やURLを創作しないでください。関連する実績がない場合は"
        "無理に紹介せず、その旨を自然な範囲で構いません。\n"
        "- 開発案件では開発・AI関連の実績を、デザイン案件ではデザイン実績を優先して紹介してください。"
        "AI×デザインの複合案件では両方の強みを自然に紹介してください。\n"
        "- 「効果を保証」「必ず売上が上がる」「採用を保証」など、結果を保証する表現は使用しないでください。\n"
        "- 極端な値下げは行わず、対応できないと考えられる内容を断言しないでください。無理な納期を提案しないでください。\n"
        "- 案件指定の質問（answers_to_client_questions）には必ず回答してください。不明点は"
        "questions_for_client に確認事項として記載してください。\n"
        "- AIが作ったと分かるような不自然に定型的な冒頭・表現は避け、案件内容を読んだ上での具体的な文章にしてください。"
        "クライアントの文章をそのまま繰り返しすぎないでください。\n"
        "- full_message は指定された構成順（挨拶→応募理由→案件内容の理解→対応できる理由→関連スキル→"
        "関連実績→進め方→納期→金額→質問への回答→確認事項→連絡姿勢→締め）を基本とし、不要な項目は省略してください。\n"
        "- short_message には full_message を要約した短縮版を作成してください。\n"
    )


def _format_skills(skills: list[dict]) -> str:
    lines = []
    for s in skills:
        exp = s.get("experience_type") or "未確認"
        lines.append(f"- {s['skill_name']}（区分: {exp}）")
    return "\n".join(lines) if lines else "（登録なし）"


def _format_candidate_portfolios(candidates: list[dict]) -> str:
    lines = []
    for p in candidates:
        url = p.get("portfolio_url") or ""
        gh = p.get("github_url") or ""
        lines.append(
            f"- id={p['id']} 「{p['title']}」区分:{p.get('portfolio_type') or '未設定'} "
            f"関連度:{p.get('relevance_score', '-')}点 URL:{url or '(なし)'} GitHub:{gh or '(なし)'} "
            f"説明:{p.get('sales_description') or p.get('description') or ''}"
        )
    return "\n".join(lines) if lines else "（関連する制作実績はありません。虚偽の実績は作成しないでください。）"


def _format_client_questions(questions: list[dict]) -> str:
    if not questions:
        return "（本文から明確な質問は検出されませんでした）"
    return "\n".join(f"- {q['question']}" for q in questions)


def build_user_prompt(
    job: dict,
    profile: dict,
    skills: list[dict],
    candidate_portfolios: list[dict],
    rule_analysis_summary: dict | None,
    price_info: dict,
    delivery_info: dict,
    client_questions: list[dict],
    tone: str,
    length_type: str,
    show_headings: bool = True,
    additional_message: str | None = None,
    exclude_content: str | None = None,
) -> str:
    body = truncate(job.get("body") or job.get("description") or "", AI_MAX_BODY_CHARS)
    char_range = LENGTH_CHAR_RANGES.get(length_type, LENGTH_CHAR_RANGES[LENGTH_MATCH_JOB])

    parts = [
        "# 案件情報",
        f"タイトル: {job.get('title') or ''}",
        f"募集形式: {job.get('job_type') or '不明'}",
        f"カテゴリ: {job.get('category') or '不明'}",
        f"予算: {job.get('budget_text') or '不明'}",
        f"応募期限: {job.get('deadline') or '不明'}",
        f"クライアント名: {job.get('client_name') or '不明'}",
        "",
        "案件本文:",
        body or "（本文情報なし）",
        "",
        "# クライアントからの質問・指定事項（本文から抽出。必ず回答すること）",
        _format_client_questions(client_questions),
        "",
        "# ユーザープロフィール",
        f"表示名: {profile.get('display_name') or ''}",
        f"職種: {profile.get('job_title') or ''}",
        f"経験段階: {profile.get('experience_level') or ''}",
        "",
        "スキル一覧:",
        _format_skills(skills),
        "",
        "# 候補となる制作実績（この中からのみ選択・紹介すること。IDは正確に使用すること）",
        _format_candidate_portfolios(candidate_portfolios),
        "",
        "# 提案する金額・納期（参考情報。文章に自然に組み込むこと）",
        f"提案金額: {price_info.get('proposed_price')}円（{price_info.get('price_reason', '')}）",
        f"提案納期: 約{delivery_info.get('recommended_delivery_days')}日（{delivery_info.get('delivery_reason', '')}）",
        "",
        "# 営業文の指定",
        f"トーン: {tone}",
        f"目標文字数: {char_range[0]}〜{char_range[1]}文字程度（厳密でなくてよい）",
        f"見出しを入れる: {'はい' if show_headings else 'いいえ'}",
    ]
    if additional_message:
        parts.append(f"追加で伝えたい内容: {additional_message}")
    if exclude_content:
        parts.append(f"営業文に含めたくない内容: {exclude_content}")

    parts += [
        "",
        "# 出力形式",
        "以下のJSONスキーマの形式のみで回答してください（値は例です。実際の内容に置き換えてください）。",
        RESPONSE_JSON_SCHEMA_TEXT,
    ]
    return "\n".join(parts)
