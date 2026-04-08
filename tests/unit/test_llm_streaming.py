"""Tests for LLM client streaming functionality."""

import pytest

from agents.llm_client import MockLLMClient, OllamaClient


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
