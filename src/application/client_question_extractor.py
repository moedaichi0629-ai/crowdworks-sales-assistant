"""案件本文から、応募者に回答を求めている質問を自動抽出する。

抽出した質問ごとに「どの実績URLで回答できそうか」の区分（デザイン／AI・開発／GitHub／一般）
を付与する。案件に関係するURLのみを回答に使うための判断材料として利用する
（要件の「クライアント質問の抽出」に対応。すべてのURLを毎回掲載しないための仕組み）。
"""
from __future__ import annotations

import re

from src.config import DEFAULT_CLIENT_QUESTION_MARKERS

_QUESTION_END_RE = re.compile(r"[？?]\s*$")
_REQUEST_PHRASES = [
    "してください", "教えてください", "記載してください", "明記してください", "ご記入ください",
    "お知らせください", "必須", "必ず記載", "ご回答ください", "提示してください",
]

_DESIGN_MARKERS = ["Illustrator", "Photoshop", "デザインポートフォリオ", "デザイン実績", "制作物"]
_GITHUB_MARKERS = ["GitHub", "ソースコード", "開発履歴", "リポジトリ"]
_AI_DEV_MARKERS = ["AI・Web", "Web制作実績", "開発実績", "アプリ実績", "使用できるツール", "使用経験"]

# 応募者自身の情報を尋ねている可能性が高いマーカー（単独でも質問として扱う）
_APPLICANT_INFO_MARKERS = [
    "自己紹介", "実績", "使用経験", "対応可能時間", "過去の制作物", "使用できるツール", "Illustrator",
    "Photoshop", "デザインポートフォリオ", "GitHub", "継続対応", "週あたりの作業時間", "ポートフォリオ",
]

MAX_QUESTIONS = 10


def _split_lines(body: str) -> list[str]:
    normalized = re.sub(r"[\r]", "", body)
    # 箇条書き記号や改行で区切って行単位にする
    parts = re.split(r"[\n・、。]", normalized)
    return [p.strip() for p in parts if p.strip()]


def _classify_answer_category(line: str) -> str:
    if any(m in line for m in _DESIGN_MARKERS):
        return "design"
    if any(m in line for m in _GITHUB_MARKERS):
        return "github"
    if any(m in line for m in _AI_DEV_MARKERS):
        return "ai_dev"
    return "general"


def extract_client_questions(job: dict) -> list[dict]:
    """案件本文からクライアントが回答を求めている質問らしき文を抽出する。

    戻り値: [{"question": str, "answer_category": "design"|"github"|"ai_dev"|"general"}]
    """
    body = job.get("body") or job.get("description") or ""
    if not body:
        return []

    lines = _split_lines(body)
    questions: list[dict] = []
    seen: set[str] = set()

    for line in lines:
        if len(line) > 120 or len(line) < 2:
            continue
        ends_with_question = bool(_QUESTION_END_RE.search(line))
        has_request_phrase = any(p in line for p in _REQUEST_PHRASES)
        has_applicant_marker = any(marker in line for marker in _APPLICANT_INFO_MARKERS)
        has_any_marker = any(marker in line for marker in DEFAULT_CLIENT_QUESTION_MARKERS)
        # 応募者自身の情報に関するマーカーは単独でも採用し、それ以外のマーカー（納期・金額等）は
        # 「〜してください」等の依頼表現を伴う場合のみ質問として扱う（クライアント側の条件記載との混同を防ぐ）
        should_include = ends_with_question or has_applicant_marker or (has_any_marker and has_request_phrase)
        if not should_include:
            continue
        if line in seen:
            continue
        seen.add(line)
        questions.append({"question": line, "answer_category": _classify_answer_category(line)})
        if len(questions) >= MAX_QUESTIONS:
            break

    return questions
