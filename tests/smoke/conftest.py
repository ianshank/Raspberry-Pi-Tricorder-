"""Smoke test fixtures — configurable target URL for container or local server."""

from __future__ import annotations

import pytest
import httpx


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--smoke-url",
        default="http://localhost:8000",
        help="Base HTTP URL for the running server (default: http://localhost:8000)",
    )
    parser.addoption(
        "--smoke-ws-url",
        default="ws://localhost:8000",
        help="Base WebSocket URL for the running server (default: ws://localhost:8000)",
    )


@pytest.fixture
def base_url(request: pytest.FixtureRequest) -> str:
    return str(request.config.getoption("--smoke-url"))


@pytest.fixture
def ws_url(request: pytest.FixtureRequest) -> str:
    return str(request.config.getoption("--smoke-ws-url"))


@pytest.fixture
def http_client(base_url: str) -> httpx.Client:
    with httpx.Client(base_url=base_url, timeout=10.0) as client:
        yield client
