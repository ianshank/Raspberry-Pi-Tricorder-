"""Tests for LLM client streaming functionality."""

from __future__ import annotations

import json
from typing import AsyncIterator

import pytest

from agents.llm_client import (
    LLMConnectionError,
    LLMTimeoutError,
    MockLLMClient,
    OllamaClient,
)


class TestMockLLMClientStream:
    """MockLLMClient.generate_stream yields words."""

    @pytest.mark.asyncio
    async def test_stream_yields_words(self):
        client = MockLLMClient(response="Hello world test")
        chunks = []
        async for chunk in client.generate_stream("test prompt"):
            chunks.append(chunk)
        assert len(chunks) == 3
        assert "".join(chunks).strip() == "Hello world test"

    @pytest.mark.asyncio
    async def test_stream_updates_call_count(self):
        client = MockLLMClient(response="One two")
        async for _ in client.generate_stream("prompt"):
            pass
        assert client.call_count == 1
        assert client.last_prompt == "prompt"

    @pytest.mark.asyncio
    async def test_stream_single_word(self):
        client = MockLLMClient(response="Single")
        chunks = []
        async for chunk in client.generate_stream("test"):
            chunks.append(chunk)
        assert len(chunks) == 1

    @pytest.mark.asyncio
    async def test_stream_empty_response(self):
        client = MockLLMClient(response="")
        chunks = []
        async for chunk in client.generate_stream("test"):
            chunks.append(chunk)
        assert chunks == []


class TestOllamaClientStreamInit:
    """OllamaClient.generate_stream is a method."""

    def test_has_generate_stream(self):
        client = OllamaClient(endpoint="http://test:11434", model="test")
        assert hasattr(client, "generate_stream")
        assert callable(client.generate_stream)


class TestOllamaClientStreamSuccess:
    """OllamaClient.generate_stream with mocked httpx streaming."""

    @pytest.mark.asyncio
    async def test_streams_ndjson_tokens(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import httpx

        ndjson_lines = [
            json.dumps({"response": "Hello ", "done": False}),
            json.dumps({"response": "world", "done": False}),
            json.dumps({"response": "", "done": True}),
        ]

        class _MockStreamResponse:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            async def aiter_lines(self) -> AsyncIterator[str]:
                for line in ndjson_lines:
                    yield line

            async def __aenter__(self) -> "_MockStreamResponse":
                return self

            async def __aexit__(self, *_: object) -> None:
                pass

        class _MockClient:
            async def __aenter__(self) -> "_MockClient":
                return self

            async def __aexit__(self, *_: object) -> None:
                pass

            def stream(self, method: str, url: str, json: dict) -> "_MockStreamResponse":
                return _MockStreamResponse()

        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _MockClient())
        client = OllamaClient(endpoint="http://test:11434", model="test")

        chunks = []
        async for chunk in client.generate_stream("test prompt"):
            chunks.append(chunk)

        assert chunks == ["Hello ", "world"]

    @pytest.mark.asyncio
    async def test_skips_empty_lines(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import httpx

        ndjson_lines = [
            "",
            "   ",
            json.dumps({"response": "token", "done": False}),
            "",
            json.dumps({"response": "", "done": True}),
        ]

        class _MockStreamResponse:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            async def aiter_lines(self) -> AsyncIterator[str]:
                for line in ndjson_lines:
                    yield line

            async def __aenter__(self) -> "_MockStreamResponse":
                return self

            async def __aexit__(self, *_: object) -> None:
                pass

        class _MockClient:
            async def __aenter__(self) -> "_MockClient":
                return self

            async def __aexit__(self, *_: object) -> None:
                pass

            def stream(self, method: str, url: str, json: dict) -> "_MockStreamResponse":
                return _MockStreamResponse()

        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _MockClient())
        client = OllamaClient()

        chunks = []
        async for chunk in client.generate_stream("test"):
            chunks.append(chunk)

        assert chunks == ["token"]

    @pytest.mark.asyncio
    async def test_skips_malformed_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import httpx

        ndjson_lines = [
            "not-valid-json",
            json.dumps({"response": "ok", "done": False}),
            "{broken",
            json.dumps({"response": "", "done": True}),
        ]

        class _MockStreamResponse:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            async def aiter_lines(self) -> AsyncIterator[str]:
                for line in ndjson_lines:
                    yield line

            async def __aenter__(self) -> "_MockStreamResponse":
                return self

            async def __aexit__(self, *_: object) -> None:
                pass

        class _MockClient:
            async def __aenter__(self) -> "_MockClient":
                return self

            async def __aexit__(self, *_: object) -> None:
                pass

            def stream(self, method: str, url: str, json: dict) -> "_MockStreamResponse":
                return _MockStreamResponse()

        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _MockClient())
        client = OllamaClient()

        chunks = []
        async for chunk in client.generate_stream("test"):
            chunks.append(chunk)

        assert chunks == ["ok"]

    @pytest.mark.asyncio
    async def test_stops_at_done_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import httpx

        ndjson_lines = [
            json.dumps({"response": "first", "done": False}),
            json.dumps({"response": "last", "done": True}),
            json.dumps({"response": "SHOULD NOT APPEAR", "done": False}),
        ]

        class _MockStreamResponse:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            async def aiter_lines(self) -> AsyncIterator[str]:
                for line in ndjson_lines:
                    yield line

            async def __aenter__(self) -> "_MockStreamResponse":
                return self

            async def __aexit__(self, *_: object) -> None:
                pass

        class _MockClient:
            async def __aenter__(self) -> "_MockClient":
                return self

            async def __aexit__(self, *_: object) -> None:
                pass

            def stream(self, method: str, url: str, json: dict) -> "_MockStreamResponse":
                return _MockStreamResponse()

        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _MockClient())
        client = OllamaClient()

        chunks = []
        async for chunk in client.generate_stream("test"):
            chunks.append(chunk)

        assert "SHOULD NOT APPEAR" not in chunks
        assert chunks == ["first", "last"]

    @pytest.mark.asyncio
    async def test_skips_empty_response_tokens(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import httpx

        ndjson_lines = [
            json.dumps({"response": "", "done": False}),
            json.dumps({"response": "real", "done": False}),
            json.dumps({"response": "", "done": True}),
        ]

        class _MockStreamResponse:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            async def aiter_lines(self) -> AsyncIterator[str]:
                for line in ndjson_lines:
                    yield line

            async def __aenter__(self) -> "_MockStreamResponse":
                return self

            async def __aexit__(self, *_: object) -> None:
                pass

        class _MockClient:
            async def __aenter__(self) -> "_MockClient":
                return self

            async def __aexit__(self, *_: object) -> None:
                pass

            def stream(self, method: str, url: str, json: dict) -> "_MockStreamResponse":
                return _MockStreamResponse()

        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _MockClient())
        client = OllamaClient()

        chunks = []
        async for chunk in client.generate_stream("test"):
            chunks.append(chunk)

        assert chunks == ["real"]


class TestOllamaClientStreamErrors:
    """Error handling for OllamaClient.generate_stream."""

    @pytest.mark.asyncio
    async def test_timeout_raises_llm_timeout_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import httpx

        class _MockClient:
            async def __aenter__(self) -> "_MockClient":
                return self

            async def __aexit__(self, *_: object) -> None:
                pass

            def stream(self, method: str, url: str, json: dict) -> "_MockStreamCtx":
                return _MockStreamCtx()

        class _MockStreamCtx:
            async def __aenter__(self) -> None:
                raise httpx.TimeoutException("stream timeout")

            async def __aexit__(self, *_: object) -> None:
                pass

        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _MockClient())
        client = OllamaClient(timeout_s=1.0)

        with pytest.raises(LLMTimeoutError, match="timed out"):
            async for _ in client.generate_stream("test"):
                pass

    @pytest.mark.asyncio
    async def test_connection_error_raises_llm_connection_error(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import httpx

        class _MockClient:
            async def __aenter__(self) -> "_MockClient":
                return self

            async def __aexit__(self, *_: object) -> None:
                pass

            def stream(self, method: str, url: str, json: dict) -> "_MockStreamCtx":
                return _MockStreamCtx()

        class _MockStreamCtx:
            async def __aenter__(self) -> None:
                raise httpx.ConnectError("refused")

            async def __aexit__(self, *_: object) -> None:
                pass

        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _MockClient())
        client = OllamaClient()

        with pytest.raises(LLMConnectionError, match="refused"):
            async for _ in client.generate_stream("test"):
                pass
