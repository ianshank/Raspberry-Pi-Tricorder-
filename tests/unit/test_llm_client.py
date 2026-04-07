"""Tests for agents.llm_client — OllamaClient and MockLLMClient."""

from __future__ import annotations

import pytest
import asyncio

from agents.llm_client import (
    LLMClient,
    LLMConnectionError,
    LLMTimeoutError,
    MockLLMClient,
    OllamaClient,
)


class TestMockLLMClient:
    def test_returns_configured_response(self) -> None:
        client = MockLLMClient(response="test output")
        result = asyncio.run(client.generate("hello"))
        assert result == "test output"

    def test_tracks_last_prompt(self) -> None:
        client = MockLLMClient()
        asyncio.run(client.generate("my prompt"))
        assert client.last_prompt == "my prompt"

    def test_tracks_call_count(self) -> None:
        client = MockLLMClient()
        asyncio.run(client.generate("a"))
        asyncio.run(client.generate("b"))
        assert client.call_count == 2

    def test_protocol_conformance(self) -> None:
        assert isinstance(MockLLMClient(), LLMClient)


class TestOllamaClient:
    def test_init_strips_trailing_slash(self) -> None:
        client = OllamaClient(endpoint="http://localhost:11434/")
        assert client.endpoint == "http://localhost:11434"

    def test_protocol_conformance(self) -> None:
        assert isinstance(OllamaClient(), LLMClient)

    @pytest.mark.asyncio
    async def test_generate_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import httpx

        class _MockResponse:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> dict:
                return {"response": "LLM says hello"}

        class _MockClient:
            async def __aenter__(self) -> "_MockClient":
                return self

            async def __aexit__(self, *_: object) -> None:
                pass

            async def post(self, url: str, json: dict) -> _MockResponse:  # noqa: ARG002
                return _MockResponse()

        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _MockClient())
        client = OllamaClient()
        result = await client.generate("test prompt")
        assert result == "LLM says hello"

    @pytest.mark.asyncio
    async def test_generate_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import httpx

        class _MockClient:
            async def __aenter__(self) -> "_MockClient":
                return self

            async def __aexit__(self, *_: object) -> None:
                pass

            async def post(self, url: str, json: dict) -> None:  # noqa: ARG002
                raise httpx.TimeoutException("timed out")

        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _MockClient())
        client = OllamaClient(timeout_s=1.0)
        with pytest.raises(LLMTimeoutError):
            await client.generate("test")

    @pytest.mark.asyncio
    async def test_generate_connection_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import httpx

        class _MockClient:
            async def __aenter__(self) -> "_MockClient":
                return self

            async def __aexit__(self, *_: object) -> None:
                pass

            async def post(self, url: str, json: dict) -> None:  # noqa: ARG002
                raise httpx.ConnectError("refused")

        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _MockClient())
        client = OllamaClient()
        with pytest.raises(LLMConnectionError):
            await client.generate("test")
