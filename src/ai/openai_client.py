"""OpenAI Chat Completions API クライアント（requestsによる直接呼び出し。SDK非依存）。"""
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

OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"


class OpenAIClient(BaseAIClient):
    provider_name = "openai"

    def complete(self, system_prompt: str, user_prompt: str, max_tokens: int = 1500) -> AIClientResponse:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }

        last_error: Exception | None = None
        for attempt in range(self.max_retry_count + 1):
            try:
                response = requests.post(
                    OPENAI_CHAT_COMPLETIONS_URL, headers=headers, json=payload,
                    timeout=self.timeout_seconds,
                )
            except requests.Timeout as exc:
                last_error = AIClientTimeoutError("OpenAI APIがタイムアウトしました。")
                continue
            except requests.RequestException as exc:
                last_error = AIClientError(f"OpenAI APIへの通信に失敗しました: {exc}")
                continue

            if response.status_code in (401, 403):
                raise AIClientAuthError("OpenAI APIの認証に失敗しました。APIキーを確認してください。")
            if response.status_code == 429:
                last_error = AIClientRateLimitError("OpenAI APIのレート制限に達しました。")
                continue
            if response.status_code != 200:
                last_error = AIClientError(f"OpenAI APIエラー（ステータス: {response.status_code}）")
                continue

            body = response.json()
            try:
                text = body["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:
                raise AIClientError(f"OpenAI APIレスポンスの形式が不正です: {exc}") from exc

            return AIClientResponse(
                text=text, provider=self.provider_name, model=self.model,
                usage=body.get("usage"), raw=body,
            )

        raise last_error or AIClientError("OpenAI APIの呼び出しに失敗しました。")
