"""Tests for admin config hot-reload router."""

import hashlib
import hmac
import json

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from mcp_server.admin import create_admin_router
from utils.config import ConfigManager, TricorderConfig
from utils.constants import ADMIN_HMAC_HEADER

HMAC_SECRET = "test-hmac-secret-key"


def _make_app_and_manager():
    """Create a fresh app + config manager pair."""
    config = TricorderConfig(
        admin={
            "enabled": True,
            "hmac_secret": HMAC_SECRET,
            "allowed_sections": ["ui", "logging", "feature_flags"],
        },
    )
    mgr = ConfigManager(config)
    app = FastAPI()
    router = create_admin_router(
        config_manager=mgr,
        hmac_secret=HMAC_SECRET,
        max_payload_bytes=65536,
    )
    app.include_router(router)
    return app, mgr


def _sign(body: bytes) -> str:
    """Compute HMAC-SHA256 of body using test secret."""
    return hmac.new(HMAC_SECRET.encode(), body, hashlib.sha256).hexdigest()


class TestGetConfig:
    @pytest.mark.asyncio
    async def test_get_config_returns_sanitized(self):
        app, _ = _make_app_and_manager()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/admin/config")
            assert resp.status_code == 200
            data = resp.json()
            assert "version" in data
            assert "logging" in data


class TestPutConfig:
    @pytest.mark.asyncio
    async def test_update_logging_level(self):
        app, mgr = _make_app_and_manager()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            body = json.dumps({"updates": {"logging": {"level": "DEBUG"}}}).encode()
            resp = await client.put(
                "/admin/config",
                content=body,
                headers={ADMIN_HMAC_HEADER: _sign(body)},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] is True
            assert "logging" in data["changes"]
            assert mgr.config.logging.level == "DEBUG"

    @pytest.mark.asyncio
    async def test_missing_hmac_header(self):
        app, _ = _make_app_and_manager()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            body = json.dumps({"updates": {"logging": {"level": "DEBUG"}}}).encode()
            resp = await client.put("/admin/config", content=body)
            assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_hmac_signature(self):
        app, _ = _make_app_and_manager()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            body = json.dumps({"updates": {"logging": {"level": "DEBUG"}}}).encode()
            resp = await client.put(
                "/admin/config",
                content=body,
                headers={ADMIN_HMAC_HEADER: "invalid-signature"},
            )
            assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_payload_too_large(self):
        config = TricorderConfig(admin={"enabled": True, "hmac_secret": HMAC_SECRET})
        mgr = ConfigManager(config)
        small_app = FastAPI()
        router = create_admin_router(
            config_manager=mgr,
            hmac_secret=HMAC_SECRET,
            max_payload_bytes=10,
        )
        small_app.include_router(router)

        transport = ASGITransport(app=small_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            body = json.dumps({"updates": {"logging": {"level": "DEBUG"}}}).encode()
            resp = await client.put(
                "/admin/config",
                content=body,
                headers={ADMIN_HMAC_HEADER: _sign(body)},
            )
            assert resp.status_code == 413

    @pytest.mark.asyncio
    async def test_invalid_json(self):
        app, _ = _make_app_and_manager()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            body = b"not-json"
            resp = await client.put(
                "/admin/config",
                content=body,
                headers={ADMIN_HMAC_HEADER: _sign(body)},
            )
            assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_missing_updates_key(self):
        app, _ = _make_app_and_manager()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            body = json.dumps({"wrong_key": {}}).encode()
            resp = await client.put(
                "/admin/config",
                content=body,
                headers={ADMIN_HMAC_HEADER: _sign(body)},
            )
            assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_disallowed_section(self):
        app, _ = _make_app_and_manager()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            body = json.dumps({"updates": {"sensors": {"i2c_devices": {}}}}).encode()
            resp = await client.put(
                "/admin/config",
                content=body,
                headers={ADMIN_HMAC_HEADER: _sign(body)},
            )
            assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_config_value(self):
        app, _ = _make_app_and_manager()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            body = json.dumps({"updates": {"logging": {"level": "NONEXISTENT"}}}).encode()
            resp = await client.put(
                "/admin/config",
                content=body,
                headers={ADMIN_HMAC_HEADER: _sign(body)},
            )
            assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_update_feature_flags(self):
        app, mgr = _make_app_and_manager()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            body = json.dumps({"updates": {"feature_flags": {"llm_enabled": True}}}).encode()
            resp = await client.put(
                "/admin/config",
                content=body,
                headers={ADMIN_HMAC_HEADER: _sign(body)},
            )
            assert resp.status_code == 200
            assert mgr.config.feature_flags.llm_enabled is True
