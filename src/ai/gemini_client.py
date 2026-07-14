"""Google Gemini API クライアント（requestsによる直接呼び出し。SDK非依存）。"""
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

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiClient(BaseAIClient):
    provider_name = "gemini"

    def complete(self, system_prompt: str, user_prompt: str, max_tokens: int = 1500) -> AIClientResponse:
        url = f"{GEMINI_BASE_URL}/{self.model}:generateContent?key={self.api_key}"
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": max_tokens,
                "responseMimeType": "application/json",
            },
        }

        last_error: Exception | None = None
        for attempt in range(self.max_retry_count + 1):
            try:
                response = requests.post(url, json=payload, timeout=self.timeout_seconds)
            except requests.Timeout:
                last_error = AIClientTimeoutError("Gemini APIがタイムアウトしました。")
                continue
            except requests.RequestException as exc:
                last_error = AIClientError(f"Gemini APIへの通信に失敗しました: {exc}")
                continue

            if response.status_code in (401, 403):
                raise AIClientAuthError("Gemini APIの認証に失敗しました。APIキーを確認してください。")
            if response.status_code == 429:
                last_error = AIClientRateLimitError("Gemini APIのレート制限に達しました。")
                continue
            if response.status_code != 200:
                last_error = AIClientError(f"Gemini APIエラー（ステータス: {response.status_code}）")
                continue

            body = response.json()
            try:
                text = body["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError, TypeError) as exc:
                raise AIClientError(f"Gemini APIレスポンスの形式が不正です: {exc}") from exc

            usage = body.get("usageMetadata")
            return AIClientResponse(
                text=text, provider=self.provider_name, model=self.model, usage=usage, raw=body,
            )

        raise last_error or AIClientError("Gemini APIの呼び出しに失敗しました。")
