"""AIプロバイダー共通インターフェース。

各プロバイダー(OpenAI/Anthropic/Gemini)は BaseAIClient を継承し、
`complete()` を実装することで analysis 層から統一的に呼び出せる。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


class AIClientError(Exception):
    """AI API呼び出しに関する汎用エラー。"""


class AIClientTimeoutError(AIClientError):
    """タイムアウトが発生した。"""


class AIClientAuthError(AIClientError):
    """認証エラー（APIキー不正・未設定など）。"""


class AIClientRateLimitError(AIClientError):
    """レート制限エラー。"""


class AIClientAPIKeyMissingError(AIClientError):
    """APIキーが設定されていない。"""


@dataclass
class AIClientResponse:
    text: str
    provider: str
    model: str
    usage: Optional[dict] = field(default=None)
    raw: Optional[dict] = field(default=None)


class BaseAIClient(ABC):
    """AIプロバイダークライアントの共通インターフェース。"""

    provider_name: str = "base"

    def __init__(self, api_key: str, model: str, timeout_seconds: float = 30, max_retry_count: int = 1):
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retry_count = max_retry_count

    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str, max_tokens: int = 1500) -> AIClientResponse:
        """system_prompt / user_prompt を送信し、テキスト応答を取得する。"""
        raise NotImplementedError
