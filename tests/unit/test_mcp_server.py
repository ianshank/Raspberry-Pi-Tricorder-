"""Unit tests for MCP server."""

import pytest
from fastapi.testclient import TestClient

from mcp_server.server import ToolRegistry, create_app


@pytest.fixture
def test_registry():
    registry = ToolRegistry()

    @registry.register(
        name="test_tool",
        description="A test tool",
        input_schema={"type": "object", "properties": {"x": {"type": "integer"}}},
    )
    def test_tool(x: int = 0):
        return {"result": x * 2}

    @registry.register(
        name="error_tool",
        description="A tool that fails",
        input_schema={"type": "object", "properties": {}},
    )
    def error_tool():
        raise RuntimeError("Intentional failure")

    return registry


@pytest.fixture
def test_client(test_registry):
    app = create_app(config={}, registry=test_registry)
    return TestClient(app)


@pytest.fixture
def auth_client():
    registry = ToolRegistry()

    @registry.register("auth_tool", "Needs auth", {"type": "object", "properties": {}})
    def auth_tool():
        return {"secret": "data"}

    app = create_app(
        config={"auth_enabled": True, "api_key": "test-key-123"},
        registry=registry,
    )
    return TestClient(app)


class TestHealthEndpoint:
    def test_health(self, test_client):
        resp = test_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert data["tools_registered"] == 2


class TestHealthDetailedEndpoint:
    def test_health_detailed_enabled(self):
        """Detailed health returns per-sensor and MQTT state."""
        registry = ToolRegistry()
        registry.register_function("t", "test", {}, lambda: 1)
        app = create_app(
            config={"mcp_server": {"health_detailed_enabled": True}},
            registry=registry,
        )
        client = TestClient(app)
        resp = client.get("/health/detailed")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "uptime_s" in data
        assert "sensors" in data
        assert "mqtt" in data
        assert data["mqtt"]["connected"] is False

    def test_health_detailed_disabled(self):
        """When health_detailed_enabled=False, returns 404."""
        registry = ToolRegistry()
        app = create_app(
            config={"mcp_server": {"health_detailed_enabled": False}},
            registry=registry,
        )
        client = TestClient(app)
        resp = client.get("/health/detailed")
        assert resp.status_code == 404


class TestAdminConfigIntegration:
    def test_admin_not_enabled_by_default(self, test_client):
        """Admin API is not mounted when admin.enabled=False (default)."""
        resp = test_client.get("/admin/config")
        assert resp.status_code == 404

    def test_admin_enabled_with_secret(self):
        """When admin.enabled=True with hmac_secret, endpoints are mounted."""
        import hashlib
        import hmac as hmac_mod
        import json

        registry = ToolRegistry()
        secret = "test-secret"
        app = create_app(
            config={
                "admin": {"enabled": True, "hmac_secret": secret},
            },
            registry=registry,
        )
        client = TestClient(app)

        # GET should work without HMAC
        resp = client.get("/admin/config")
        assert resp.status_code == 200
        assert "version" in resp.json()

        # PUT with valid HMAC should work
        body = json.dumps({"updates": {"logging": {"level": "DEBUG"}}}).encode()
        sig = hmac_mod.new(secret.encode(), body, hashlib.sha256).hexdigest()
        resp = client.put(
            "/admin/config",
            content=body,
            headers={"X-Tricorder-HMAC": sig},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_admin_enabled_without_secret_not_mounted(self):
        """Admin enabled but no hmac_secret → admin API NOT mounted."""
        registry = ToolRegistry()
        app = create_app(
            config={"admin": {"enabled": True}},
            registry=registry,
        )
        client = TestClient(app)
        resp = client.get("/admin/config")
        assert resp.status_code == 404


class TestToolsEndpoint:
    def test_list_tools(self, test_client):
        resp = test_client.get("/tools")
        assert resp.status_code == 200
        tools = resp.json()
        assert len(tools) == 2
        names = [t["name"] for t in tools]
        assert "test_tool" in names
        assert "error_tool" in names

    def test_tool_schema(self, test_client):
        resp = test_client.get("/tools")
        tools = resp.json()
        test_tool = [t for t in tools if t["name"] == "test_tool"][0]
        assert "inputSchema" in test_tool
        assert "description" in test_tool


class TestToolCallEndpoint:
    def test_call_success(self, test_client):
        resp = test_client.post("/tools/call", json={
            "name": "test_tool",
            "arguments": {"x": 5},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["isError"] is False
        assert data["content"]["result"] == 10

    def test_call_unknown_tool(self, test_client):
        resp = test_client.post("/tools/call", json={
            "name": "nonexistent",
            "arguments": {},
        })
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Tool not found"

    def test_call_error_tool(self, test_client):
        resp = test_client.post("/tools/call", json={
            "name": "error_tool",
            "arguments": {},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["isError"] is True
        assert data["content"]["error"] == "Tool call failed. Check logs for details."

    def test_call_default_args(self, test_client):
        resp = test_client.post("/tools/call", json={
            "name": "test_tool",
            "arguments": {},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"]["result"] == 0


class TestToolRegistry:
    def test_register_decorator(self):
        registry = ToolRegistry()

        @registry.register("my_tool", "desc", {"type": "object"})
        def my_func():
            return 42

        assert registry.has_tool("my_tool")
        assert registry.tool_count == 1

    def test_register_function(self):
        registry = ToolRegistry()
        registry.register_function("fn_tool", "desc", {"type": "object"}, lambda: 99)
        assert registry.has_tool("fn_tool")

    def test_list_tools(self):
        registry = ToolRegistry()
        registry.register_function("a", "desc a", {}, lambda: 1)
        registry.register_function("b", "desc b", {}, lambda: 2)
        tools = registry.list_tools()
        assert len(tools) == 2

    @pytest.mark.asyncio
    async def test_call_sync(self):
        registry = ToolRegistry()
        registry.register_function("sync_tool", "sync", {}, lambda: "ok")
        result = await registry.call("sync_tool", {})
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_call_async(self):
        registry = ToolRegistry()

        async def async_func():
            return "async_ok"

        registry.register_function("async_tool", "async", {}, async_func)
        result = await registry.call("async_tool", {})
        assert result == "async_ok"

    @pytest.mark.asyncio
    async def test_call_unknown(self):
        registry = ToolRegistry()
        with pytest.raises(KeyError):
            await registry.call("nope", {})

    def test_call_sync_helper(self):
        registry = ToolRegistry()
        registry.register_function("sync_tool", "sync", {}, lambda: "ok")
        assert registry.call_sync("sync_tool", {}) == "ok"

    def test_call_sync_rejects_async(self):
        registry = ToolRegistry()

        async def async_func():
            return "async_ok"

        registry.register_function("async_tool", "async", {}, async_func)
        with pytest.raises(RuntimeError):
            registry.call_sync("async_tool", {})


class TestAuthMiddleware:
    def test_health_no_auth_required(self, auth_client):
        resp = auth_client.get("/health")
        assert resp.status_code == 200

    def test_tools_requires_auth(self, auth_client):
        resp = auth_client.get("/tools")
        assert resp.status_code == 401

    def test_tools_with_valid_auth(self, auth_client):
        resp = auth_client.get("/tools", headers={"Authorization": "Bearer test-key-123"})
        assert resp.status_code == 200

    def test_tools_with_invalid_auth(self, auth_client):
        resp = auth_client.get("/tools", headers={"Authorization": "Bearer wrong-key"})
        assert resp.status_code == 401

    def test_tools_denied_when_auth_enabled_without_key(self):
        registry = ToolRegistry()

        @registry.register("auth_tool", "Needs auth", {"type": "object", "properties": {}})
        def auth_tool():
            return {"secret": "data"}

        app = create_app(config={"auth_enabled": True}, registry=registry)
        client = TestClient(app)

        resp = client.get("/tools")
        assert resp.status_code == 503
