"""Smoke tests for a running Tricorder server (Docker or local).

Run against a container:
    pytest tests/smoke/ -v -m smoke --smoke-url http://localhost:8000

All tests should complete in under 30 seconds total.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone

import httpx
import pytest
import websockets


@pytest.mark.smoke
class TestContainerSmoke:
    def test_health_endpoint_returns_200(self, http_client: httpx.Client) -> None:
        resp = http_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert isinstance(data["tools_registered"], int)
        assert data["tools_registered"] >= 0

    def test_tool_list_returns_tools(self, http_client: httpx.Client) -> None:
        resp = http_client.get("/tools")
        assert resp.status_code == 200
        tools = resp.json()
        assert isinstance(tools, list)
        if tools:
            first = tools[0]
            assert "name" in first
            assert "description" in first
            assert "inputSchema" in first

    def test_ui_config_returns_valid_json(self, http_client: httpx.Client) -> None:
        resp = http_client.get("/ui/config.json")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        assert "poll_interval_ms" in data
        assert "ws_path" in data
        assert "theme" in data

    def test_websocket_sensor_stream(self, ws_url: str) -> None:
        async def _connect_once() -> dict:
            uri = f"{ws_url}/ws/sensors"
            async with websockets.connect(uri) as ws:
                raw = await asyncio.wait_for(ws.recv(), timeout=15.0)
                return json.loads(raw)

        data = None
        for attempt in range(3):
            try:
                data = asyncio.run(_connect_once())
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(1)

        assert data is not None
        assert "timestamp" in data
        assert "readings" in data

    def test_health_timestamp_is_recent(self, http_client: httpx.Client) -> None:
        resp = http_client.get("/health")
        assert resp.status_code == 200
        ts_str = resp.json()["timestamp"]
        ts = datetime.fromisoformat(ts_str)
        now = datetime.now(timezone.utc)
        delta = abs((now - ts).total_seconds())
        assert delta < 120, f"Health timestamp {ts_str} is {delta:.0f}s from now"

    def test_root_responds(self, http_client: httpx.Client) -> None:
        resp = http_client.get("/", follow_redirects=False)
        assert resp.status_code in (200, 301, 302, 307, 308)
