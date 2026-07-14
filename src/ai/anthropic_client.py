"""Anthropic Claude Messages API クライアント（requestsによる直接呼び出し。SDK非依存）。"""
from __future__ import annotations

import requests

from src.ai.base_client import (
    AIClientAuthError,
    AIClientError,
    AIClientRateLimitError,
    AIClientResponse,
    AIClientTimeoutError,
    BaseAIClient,
)

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"


class AnthropicClient(BaseAIClient):
    provider_name = "anthropic"

    def complete(self, system_prompt: str, user_prompt: str, max_tokens: int = 1500) -> AIClientResponse:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_API_VERSION,
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.2,
        }

        last_error: Exception | None = None
        for attempt in range(self.max_retry_count + 1):
            try:
                response = requests.post(
                    ANTHROPIC_MESSAGES_URL, headers=headers, json=payload,
                    timeout=self.timeout_seconds,
                )
            except requests.Timeout:
                last_error = AIClientTimeoutError("Anthropic APIがタイムアウトしました。")
                continue
            except requests.RequestException as exc:
                last_error = AIClientError(f"Anthropic APIへの通信に失敗しました: {exc}")
                continue

            if response.status_code in (401, 403):
                raise AIClientAuthError("Anthropic APIの認証に失敗しました。APIキーを確認してください。")
            if response.status_code == 429:
                last_error = AIClientRateLimitError("Anthropic APIのレート制限に達しました。")
                continue
            if response.status_code != 200:
                last_error = AIClientError(f"Anthropic APIエラー（ステータス: {response.status_code}）")
                continue

            body = response.json()
            try:
                text = "".join(
                    block.get("text", "") for block in body.get("content", []) if block.get("type") == "text"
                )
                if not text:
                    raise KeyError("content")
            except (KeyError, TypeError) as exc:
                raise AIClientError(f"Anthropic APIレスポンスの形式が不正です: {exc}") from exc

            return AIClientResponse(
                text=text, provider=self.provider_name, model=self.model,
                usage=body.get("usage"), raw=body,
            )

        raise last_error or AIClientError("Anthropic APIの呼び出しに失敗しました。")
