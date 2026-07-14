"""設定内容に応じてAIクライアントを組み立てるファクトリ。

APIキーが未設定・プロバイダーが"none"の場合はNoneを返す。
呼び出し側はNoneの場合、ルールベース分析のみで処理を継続すること。
"""
from __future__ import annotations

import os

from src.ai.anthropic_client import AnthropicClient
from src.ai.base_client import BaseAIClient
from src.ai.gemini_client import GeminiClient
from src.ai.openai_client import OpenAIClient
from src.config import (
    AI_PROVIDER_ANTHROPIC,
    AI_PROVIDER_GEMINI,
    AI_PROVIDER_NONE,
    AI_PROVIDER_OPENAI,
    DEFAULT_MODELS,
)
from src.logger import get_logger

logger = get_logger()

_CLIENT_CLASSES: dict[str, type[BaseAIClient]] = {
    AI_PROVIDER_OPENAI: OpenAIClient,
    AI_PROVIDER_ANTHROPIC: AnthropicClient,
    AI_PROVIDER_GEMINI: GeminiClient,
}

_API_KEY_ENV_VARS = {
    AI_PROVIDER_OPENAI: "OPENAI_API_KEY",
    AI_PROVIDER_ANTHROPIC: "ANTHROPIC_API_KEY",
    AI_PROVIDER_GEMINI: "GEMINI_API_KEY",
}


def get_ai_client(
    provider: str,
    models: dict | None = None,
    timeout_seconds: float = 30,
    max_retry_count: int = 1,
) -> BaseAIClient | None:
    """設定に応じたAIクライアントを返す。利用できない場合はNoneを返す（アプリは停止させない）。"""
    if not provider or provider == AI_PROVIDER_NONE:
        return None

    if provider not in _CLIENT_CLASSES:
        logger.warning("未対応のAIプロバイダーが指定されました: %s", provider)
        return None

    api_key = os.getenv(_API_KEY_ENV_VARS[provider], "").strip()
    if not api_key:
        logger.warning("AIプロバイダー(%s)のAPIキーが未設定のため、ルールベース分析のみ利用します。", provider)
        return None

    models = models or DEFAULT_MODELS
    model = models.get(provider) or DEFAULT_MODELS.get(provider)

    client_class = _CLIENT_CLASSES[provider]
    return client_class(
        api_key=api_key, model=model, timeout_seconds=timeout_seconds, max_retry_count=max_retry_count,
    )


def is_provider_available(provider: str) -> bool:
    """指定プロバイダーのAPIキーが環境変数に設定されているか判定する。"""
    if not provider or provider == AI_PROVIDER_NONE:
        return False
    env_var = _API_KEY_ENV_VARS.get(provider)
    return bool(env_var and os.getenv(env_var, "").strip())
