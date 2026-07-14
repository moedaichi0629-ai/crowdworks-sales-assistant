"""AI案件分析用のプロンプトを組み立てる。"""
from __future__ import annotations

import json

from src.config import AI_MAX_BODY_CHARS
from src.utils import truncate

RESPONSE_JSON_SCHEMA_TEXT = """
{
  "suitability_score": 0,
  "recommendation": "strong_apply | apply | consider | skip",
  "difficulty": "beginner | intermediate | advanced | expert",
  "confidence": 0,
  "summary": "",
  "client_needs": [],
  "required_skills": [],
  "matched_skills": [],
  "missing_skills": [],
  "matched_portfolio": [],
  "estimated_hours_min": 0,
  "estimated_hours_max": 0,
  "estimated_days": 0,
  "budget_evaluation": "low | fair | good | unknown",
  "strengths": [],
  "concerns": [],
  "questions_before_applying": [],
  "application_strategy": "",
  "analysis_reason": "",
  "safety_score": 0,
  "risk_level": "low | medium | high | critical",
  "detected_risks": [],
  "risk_reasons": [],
  "recommended_action": "proceed | review | avoid",
  "safety_summary": ""
}
""".strip()


def build_system_prompt() -> str:
    return (
        "あなたはクラウドソーシングの案件を分析する、経験豊富な受注アドバイザーです。"
        "与えられた案件情報とユーザーのスキルプロフィールを比較し、応募する価値があるかどうかを"
        "客観的かつ誠実に分析してください。\n\n"
        "厳守事項:\n"
        "- 必ず指定されたJSON形式のみで回答してください。JSON以外の説明文は一切含めないでください。\n"
        "- ユーザーの実績を過大評価しないでください。スキルの経験区分（学習経験・個人開発経験・"
        "公開実績・実案件経験・未確認）を区別し、実務経験が確認できないスキルを『実務経験あり』と"
        "断定しないでください。\n"
        "- 案件本文に明記されていない内容を過度に推測しないでください。不明な場合は素直に『不明』"
        "『要確認』として扱ってください。\n"
        "- 不足しているスキルについては、短期間の学習・調査で対応可能なものと、受注を避けるべき"
        "レベルのものを区別してください。\n"
        "- 危険・低品質案件の兆候（外部連絡先誘導、購入要求、初期費用要求、無報酬テスト、"
        "極端に低い報酬、不明確な業務内容等）がないか、文脈も踏まえて慎重に判定してください。"
        "キーワードが含まれているだけで自動的に危険と判定せず、文脈上問題がないかも考慮してください。\n"
    )


def _format_skills(skills: list[dict]) -> str:
    lines = []
    for s in skills:
        exp = s.get("experience_type") or "未確認"
        lines.append(f"- {s['skill_name']}（区分: {exp}, 習熟度: {s.get('proficiency_level') or '未設定'}）")
    return "\n".join(lines) if lines else "（登録なし）"


def _format_portfolios(portfolios: list[dict]) -> str:
    lines = []
    for p in portfolios:
        techs = ", ".join(p.get("technologies") or [])
        lines.append(f"- {p['title']}: {p.get('description') or ''}（使用技術: {techs}）")
    return "\n".join(lines) if lines else "（登録なし）"


def build_user_prompt(
    job: dict,
    profile: dict,
    skills: list[dict],
    portfolios: list[dict],
    rule_result: dict,
    danger_hits: list[str],
) -> str:
    """案件情報・プロフィール・ルールベース判定結果からユーザープロンプトを組み立てる。"""
    body = truncate(job.get("body") or job.get("description") or "", AI_MAX_BODY_CHARS)

    parts = [
        "# 案件情報",
        f"タイトル: {job.get('title') or ''}",
        f"募集形式: {job.get('job_type') or '不明'}",
        f"カテゴリ: {job.get('category') or '不明'}",
        f"予算: {job.get('budget_text') or '不明'}",
        f"応募期限: {job.get('deadline') or '不明'}",
        f"応募人数: {job.get('applicant_count') if job.get('applicant_count') is not None else '不明'}",
        f"クライアント名: {job.get('client_name') or '不明'}",
        f"クライアント評価: {job.get('client_rating') if job.get('client_rating') is not None else '不明'}",
        f"本人確認: {'済み' if job.get('identity_verified') else '未確認/不明'}",
        "",
        "案件本文:",
        body or "（本文情報なし）",
        "",
        "# ユーザープロフィール",
        f"表示名: {profile.get('display_name') or ''}",
        f"職種: {profile.get('job_title') or ''}",
        f"経験段階: {profile.get('experience_level') or ''}",
        f"1日あたりの作業時間目安: {profile.get('daily_available_hours') or ''}",
        "",
        "スキル一覧:",
        _format_skills(skills),
        "",
        "制作実績:",
        _format_portfolios(portfolios),
        "",
        "対応が難しい条件（初期設定）:",
        "、".join((profile.get("difficult_conditions") or {}).get("difficult_conditions", [])) or "なし",
        "",
        "# ルールベース一次判定結果（参考情報）",
        f"ルールベーススコア: {rule_result.get('score')}点",
        "根拠: " + " / ".join(rule_result.get("breakdown_labels", [])),
        "",
        "検出された危険キーワード（単純一致・文脈未判定。参考情報として扱い、文脈判定と併用すること）:",
        "、".join(danger_hits) if danger_hits else "なし",
        "",
        "# 出力形式",
        "以下のJSONスキーマの形式のみで回答してください（値は例です。実際の分析結果に置き換えてください）。",
        RESPONSE_JSON_SCHEMA_TEXT,
    ]
    return "\n".join(parts)
