"""AIクライアント(OpenAI/Anthropic/Gemini)のテスト。実際の有料APIは呼び出さず、モックを使用する。"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from src.ai.base_client import (
    AIClientAuthError,
    AIClientError,
    AIClientRateLimitError,
    AIClientTimeoutError,
)
from src.ai.openai_client import OpenAIClient
from src.ai.provider_factory import get_ai_client


def _mock_response(status_code: int, json_body: dict) -> MagicMock:
    m = MagicMock()
    m.status_code = status_code
    m.json.return_value = json_body
    return m


def test_openai_normal_response():
    body = {"choices": [{"message": {"content": '{"a": 1}'}}], "usage": {"total_tokens": 10}}
    with patch("src.ai.openai_client.requests.post", return_value=_mock_response(200, body)):
        client = OpenAIClient(api_key="k", model="m", timeout_seconds=5, max_retry_count=1)
        response = client.complete("system", "user")
    assert response.text == '{"a": 1}'
    assert response.usage["total_tokens"] == 10
    assert response.provider == "openai"


def test_openai_timeout_raises():
    with patch("src.ai.openai_client.requests.post", side_effect=requests.Timeout()):
        client = OpenAIClient(api_key="k", model="m", timeout_seconds=5, max_retry_count=0)
        with pytest.raises(AIClientTimeoutError):
            client.complete("system", "user")


def test_openai_auth_error_raises():
    with patch("src.ai.openai_client.requests.post", return_value=_mock_response(401, {})):
        client = OpenAIClient(api_key="bad-key", model="m", timeout_seconds=5, max_retry_count=1)
        with pytest.raises(AIClientAuthError):
            client.complete("system", "user")


def test_openai_rate_limit_raises():
    with patch("src.ai.openai_client.requests.post", return_value=_mock_response(429, {})):
        client = OpenAIClient(api_key="k", model="m", timeout_seconds=5, max_retry_count=0)
        with pytest.raises(AIClientRateLimitError):
            client.complete("system", "user")


def test_openai_malformed_response_body_raises():
    body = {"unexpected": "shape"}
    with patch("src.ai.openai_client.requests.post", return_value=_mock_response(200, body)):
        client = OpenAIClient(api_key="k", model="m", timeout_seconds=5, max_retry_count=0)
        with pytest.raises(AIClientError):
            client.complete("system", "user")


def test_provider_factory_returns_none_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = get_ai_client("openai")
    assert client is None


def test_provider_factory_returns_none_for_provider_none():
    client = get_ai_client("none")
    assert client is None


def test_provider_factory_returns_client_when_api_key_present(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    client = get_ai_client("openai")
    assert client is not None
    assert client.provider_name == "openai"
