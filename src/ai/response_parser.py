"""AIレスポンス(テキスト)からJSONを抽出し、構造化データへ変換する。

壊れたJSONへの対応順序:
    1. そのままJSONとして解析
    2. Markdownコードブロックを除去して解析
    3. 前後の文章を除去し、最初の{から最後の}までを抽出して解析
    4. 末尾カンマなど軽微な形式エラーを修正して解析
    5. すべて失敗した場合は ResponseParseError を送出する（呼び出し側で再生成 or フォールバック）
"""
from __future__ import annotations

import json
import re

from src.ai.schemas import AIAnalysisResponse


class ResponseParseError(Exception):
    """AIレスポンスからJSONを抽出・解析できなかった。"""


_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")


def extract_json(text: str) -> dict:
    """AIの応答テキストからJSONオブジェクトを抽出する。"""
    if not text or not text.strip():
        raise ResponseParseError("AIの応答が空でした。")

    candidates: list[str] = [text.strip()]

    fence_match = _CODE_FENCE_RE.search(text)
    if fence_match:
        candidates.append(fence_match.group(1).strip())

    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidates.append(text[first_brace : last_brace + 1])

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc
            fixed = _TRAILING_COMMA_RE.sub(r"\1", candidate)
            if fixed != candidate:
                try:
                    return json.loads(fixed)
                except json.JSONDecodeError as exc2:
                    last_error = exc2

    raise ResponseParseError(f"AIの応答からJSONを抽出できませんでした: {last_error}")


def parse_ai_response(text: str) -> AIAnalysisResponse:
    """AIの応答テキストを検証済みの構造化データへ変換する。"""
    data = extract_json(text)
    if not isinstance(data, dict):
        raise ResponseParseError("AIの応答はJSONオブジェクトである必要があります。")
    return AIAnalysisResponse.model_validate(data)
