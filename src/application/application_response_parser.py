"""営業文生成AIレスポンス(テキスト)からJSONを抽出し、構造化データへ変換する。

壊れたJSONへの対応は src.ai.response_parser の抽出ロジック（コードブロック除去 →
前後除去 → 末尾カンマ修正の順）を再利用する。
"""
from __future__ import annotations

from src.ai.response_parser import ResponseParseError, extract_json
from src.application.application_schemas import ApplicationDraftResponse

__all__ = ["ResponseParseError", "parse_application_response"]


def parse_application_response(text: str) -> ApplicationDraftResponse:
    data = extract_json(text)
    if not isinstance(data, dict):
        raise ResponseParseError("AIの応答はJSONオブジェクトである必要があります。")
    return ApplicationDraftResponse.model_validate(data)
