"""LLM client abstraction for agent report synthesis.

Provides an ``LLMClient`` protocol plus a concrete ``OllamaClient`` that talks
to the Ollama ``/api/generate`` endpoint. A ``MockLLMClient`` is included for
deterministic testing without mocking frameworks.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, AsyncIterator, Optional, Protocol, runtime_checkable

from utils.constants import DEFAULT_LLM_ENDPOINT, DEFAULT_LLM_MAX_TOKENS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class LLMError(Exception):
    """Base exception for LLM client errors."""


class LLMTimeoutError(LLMError):
    """Raised when the LLM endpoint does not respond within the timeout."""


class LLMConnectionError(LLMError):
    """Raised when the LLM endpoint is unreachable."""


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class LLMClient(Protocol):
    """Minimal async interface for text generation."""

    async def generate(
        self,
        prompt: str,
        temperature: float = 0.1,
        max_tokens: int = DEFAULT_LLM_MAX_TOKENS,
    ) -> str:
        """Generate text from an LLM. Returns the generated text."""
        ...


# ---------------------------------------------------------------------------
# Ollama implementation
# ---------------------------------------------------------------------------

class OllamaClient:
    """Async client for the Ollama ``/api/generate`` endpoint.

    Uses ``httpx`` for HTTP communication (already a project dependency).
    """

    def __init__(
        self,
        endpoint: str = DEFAULT_LLM_ENDPOINT,
        model: str = "qwen2.5:3b",
        timeout_s: float = 30.0,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s
        logger.info("OllamaClient initialised: endpoint=%s, model=%s", self.endpoint, self.model)

    async def generate(
        self,
        prompt: str,
        temperature: float = 0.1,
        max_tokens: int = DEFAULT_LLM_MAX_TOKENS,
    ) -> str:
        import httpx

        url = f"{self.endpoint}/api/generate"
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        logger.debug("LLM generate request: model=%s, prompt_len=%d", self.model, len(prompt))
        start = time.monotonic()

        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
        except httpx.TimeoutException as exc:
            logger.warning("LLM generate timed out after %.1fs", self.timeout_s)
            raise LLMTimeoutError(
                f"Ollama timed out after {self.timeout_s}s"
            ) from exc
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            logger.warning("LLM generate connection error: %s", exc)
            raise LLMConnectionError(str(exc)) from exc

        data = resp.json()
        text = str(data.get("response", ""))
        elapsed = time.monotonic() - start
        logger.debug("LLM generate response: %d chars in %.1fs", len(text), elapsed)
        return text

    async def generate_stream(
        self,
        prompt: str,
        temperature: float = 0.1,
        max_tokens: int = DEFAULT_LLM_MAX_TOKENS,
    ) -> AsyncIterator[str]:
        """Stream tokens from Ollama using ``"stream": True``.

        Yields text chunks as they arrive from the NDJSON stream.
        """
        import httpx

        url = f"{self.endpoint}/api/generate"
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        logger.debug("LLM stream request: model=%s, prompt_len=%d", self.model, len(prompt))
        start = time.monotonic()

        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                async with client.stream("POST", url, json=payload) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                            text = chunk.get("response", "")
                            if text:
                                yield text
                            if chunk.get("done", False):
                                break
                        except json.JSONDecodeError:
                            logger.debug("LLM stream: skipping malformed JSON line")
                            continue
        except httpx.TimeoutException as exc:
            logger.warning("LLM stream timed out after %.1fs", self.timeout_s)
            raise LLMTimeoutError(
                f"Ollama stream timed out after {self.timeout_s}s"
            ) from exc
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            logger.warning("LLM stream connection error: %s", exc)
            raise LLMConnectionError(str(exc)) from exc

        elapsed = time.monotonic() - start
        logger.debug("LLM stream completed in %.1fs", elapsed)


# ---------------------------------------------------------------------------
# Mock for testing
# ---------------------------------------------------------------------------

class MockLLMClient:
    """Deterministic mock that returns a configurable static string."""

    def __init__(self, response: str = "Mock LLM response.") -> None:
        self._response = response
        self.last_prompt: Optional[str] = None
        self.call_count = 0

    async def generate(
        self,
        prompt: str,
        temperature: float = 0.1,
        max_tokens: int = DEFAULT_LLM_MAX_TOKENS,
    ) -> str:
        self.last_prompt = prompt
        self.call_count += 1
        return self._response

    async def generate_stream(
        self,
        prompt: str,
        temperature: float = 0.1,
        max_tokens: int = DEFAULT_LLM_MAX_TOKENS,
    ) -> AsyncIterator[str]:
        """Yield response word-by-word for testing."""
        self.last_prompt = prompt
        self.call_count += 1
        for word in self._response.split():
            yield word + " "
