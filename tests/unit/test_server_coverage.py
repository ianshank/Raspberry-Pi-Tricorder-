"""Tests for previously-uncovered server.py paths.

Covers:
- _severity_from_score with custom thresholds
- _coerce_bool edge cases
- _coerce_float edge cases
- Tool call KeyError, TypeError, generic Exception paths
- Invalid ws/agent/ack path fallbacks
- call_sync with async tool
- Malformed ui_config type
- Agent chat: agent_runner None, agent raises, anomaly_score None
- _extract_anomaly_summary with custom severity thresholds
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch

from mcp_server.anomaly_helpers import (
    coerce_bool as _coerce_bool,
    coerce_float as _coerce_float,
    severity_from_score as _severity_from_score,
    extract_anomaly_summary as _extract_anomaly_summary,
)
from mcp_server.server import (
    ToolRegistry,
    create_app,
    MCPServerError,
    ToolExecutionError,
    AuthenticationError,
    _resolve_static_dir,
)


# ========== Pure-function unit tests ==========


class TestSeverityFromScore:
    """Covers _severity_from_score with custom thresholds (new behaviour)."""

    def test_none_is_unknown(self):
        assert _severity_from_score(None) == "UNKNOWN"

    def test_default_thresholds_critical(self):
        assert _severity_from_score(0.95) == "CRITICAL"

    def test_default_thresholds_high(self):
        assert _severity_from_score(0.80) == "HIGH"

    def test_default_thresholds_medium(self):
        assert _severity_from_score(0.60) == "MEDIUM"

    def test_default_thresholds_low(self):
        assert _severity_from_score(0.30) == "LOW"

    def test_custom_thresholds(self):
        thresholds = {"critical": 0.95, "high": 0.80, "medium": 0.60}
        assert _severity_from_score(0.90, thresholds) == "HIGH"
        assert _severity_from_score(0.96, thresholds) == "CRITICAL"
        assert _severity_from_score(0.70, thresholds) == "MEDIUM"
        assert _severity_from_score(0.40, thresholds) == "LOW"

    def test_boundary_at_critical(self):
        assert _severity_from_score(0.9) == "CRITICAL"

    def test_boundary_just_below_critical(self):
        assert _severity_from_score(0.899) == "HIGH"


class TestCoerceBool:
    """Covers _coerce_bool edge cases (lines 172-183)."""

    def test_true_bool(self):
        assert _coerce_bool(True) is True

    def test_false_bool(self):
        assert _coerce_bool(False) is False

    def test_string_true(self):
        assert _coerce_bool("true") is True
        assert _coerce_bool("YES") is True
        assert _coerce_bool("1") is True
        assert _coerce_bool("on") is True

    def test_string_false(self):
        assert _coerce_bool("false") is False
        assert _coerce_bool("NO") is False
        assert _coerce_bool("0") is False
        assert _coerce_bool("off") is False

    def test_int_truthy(self):
        assert _coerce_bool(1) is True

    def test_int_falsy(self):
        assert _coerce_bool(0) is False

    def test_none_returns_none(self):
        assert _coerce_bool(None) is None

    def test_unknown_string_returns_none(self):
        assert _coerce_bool("maybe") is None


class TestCoerceFloat:
    """Covers _coerce_float edge cases (lines 162-169)."""

    def test_valid_float(self):
        assert _coerce_float(1.5) == 1.5

    def test_string_float(self):
        assert _coerce_float("0.75") == 0.75

    def test_none_returns_none(self):
        assert _coerce_float(None) is None

    def test_nan_returns_none(self):
        assert _coerce_float(float("nan")) is None

    def test_inf_returns_none(self):
        assert _coerce_float(float("inf")) is None

    def test_string_non_numeric_returns_none(self):
        assert _coerce_float("bad") is None


class TestResolveStaticDir:
    def test_prefers_current_working_directory_for_relative_paths(self, monkeypatch, tmp_path):
        static_dir = tmp_path / "src" / "ui" / "static"
        static_dir.mkdir(parents=True)

        monkeypatch.chdir(tmp_path)

        assert _resolve_static_dir("src/ui/static") == static_dir.resolve()


class TestExtractAnomalySummaryWithThresholds:
    """_extract_anomaly_summary now accepts severity_thresholds."""

    def test_custom_thresholds_applied(self):
        scan = {"output": {"anomaly_score": 0.80, "is_anomaly": True}}
        # With default thresholds, 0.80 is HIGH.
        # With custom thresholds where high=0.85, 0.80 is MEDIUM.
        result = _extract_anomaly_summary(
            scan,
            None,
            fallback_threshold=0.75,
            severity_thresholds={"critical": 0.95, "high": 0.85, "medium": 0.5},
        )
        assert result["severity"] == "MEDIUM"

    def test_no_thresholds_uses_defaults(self):
        scan = {"output": {"anomaly_score": 0.80}}
        result = _extract_anomaly_summary(scan, None, fallback_threshold=0.75)
        assert result["severity"] == "HIGH"

    def test_score_from_history_when_scan_empty(self):
        history = {"anomaly_score": 0.92}
        result = _extract_anomaly_summary({}, history, fallback_threshold=0.75)
        assert result["anomaly_score"] == 0.92
        assert result["severity"] == "CRITICAL"

    def test_is_anomaly_fallback_from_score(self):
        """is_anomaly not in payload → derived from score vs fallback_threshold."""
        scan = {"output": {"anomaly_score": 0.80}}
        result = _extract_anomaly_summary(scan, None, fallback_threshold=0.75)
        assert result["is_anomaly"] is True

    def test_is_anomaly_false_below_threshold(self):
        scan = {"output": {"anomaly_score": 0.50}}
        result = _extract_anomaly_summary(scan, None, fallback_threshold=0.75)
        assert result["is_anomaly"] is False

    def test_all_none_scores(self):
        result = _extract_anomaly_summary({}, None, fallback_threshold=0.75)
        assert result["anomaly_score"] is None
        assert result["is_anomaly"] is False
        assert result["severity"] == "UNKNOWN"


# ========== Integration tests via TestClient ==========


@pytest.fixture
def base_registry():
    registry = ToolRegistry()

    def sync_tool():
        return {"ok": True}

    registry.register_function("sync_tool", "Sync tool", {"type": "object"}, sync_tool)

    async def async_tool():
        return {"ok": True}

    registry.register_function("async_tool", "Async tool", {"type": "object"}, async_tool)
    return registry


@pytest.fixture
def base_client(base_registry):
    app = create_app(config={}, registry=base_registry)
    return TestClient(app)


class TestToolCallErrors:
    """Covers lines 537-546 — KeyError, TypeError, generic Exception."""

    def test_tool_not_found_404(self, base_client):
        """KeyError → 404."""
        resp = base_client.post("/tools/call", json={"name": "nonexistent", "arguments": {}})
        assert resp.status_code == 404

    def test_tool_wrong_args_400(self, base_client):
        """TypeError → 400: pass wrong keyword arg."""
        resp = base_client.post(
            "/tools/call",
            json={"name": "sync_tool", "arguments": {"unexpected_kwarg": 1}},
        )
        assert resp.status_code == 400

    def test_tool_generic_error_returns_error_response(self):
        """RuntimeError inside tool → isError=True response."""
        registry = ToolRegistry()

        def failing_tool():
            raise RuntimeError("boom")

        registry.register_function("fail", "fail", {"type": "object"}, failing_tool)
        app = create_app(config={}, registry=registry)
        client = TestClient(app)
        resp = client.post("/tools/call", json={"name": "fail", "arguments": {}})
        assert resp.status_code == 200
        assert resp.json()["isError"] is True


class TestCallSyncAsyncTool:
    """Covers ToolRegistry.call_sync with an async tool (line 128)."""

    def test_call_sync_async_raises(self, base_registry):
        with pytest.raises(RuntimeError, match="async"):
            base_registry.call_sync("async_tool", {})


class TestInvalidPathFallbacks:
    """Covers lines 410-453 — bad ws/agent/ack path strings fall back to defaults."""

    def _make_client_with_paths(self, ws="bad_path", anomaly_ws="bad_anomaly", agent="bad_agent", ack="bad_ack"):
        registry = ToolRegistry()
        cfg = {
            "ui": {
                "ws_path": ws,
                "anomaly_ws_path": anomaly_ws,
                "agent_chat_path": agent,
                "anomaly_ack_path": ack,
                "enabled": False,
            }
        }
        app = create_app(config=cfg, registry=registry)
        return TestClient(app)

    def test_bad_ws_path_falls_back_and_health_ok(self):
        client = self._make_client_with_paths()
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_valid_paths_accepted(self):
        registry = ToolRegistry()
        cfg = {
            "ui": {
                "ws_path": "/ws/sensors",
                "anomaly_ws_path": "/ws/anomalies",
                "agent_chat_path": "/ui/agent/chat",
                "anomaly_ack_path": "/ui/anomalies/ack",
                "enabled": False,
            }
        }
        app = create_app(config=cfg, registry=registry)
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200


class TestMalformedUiConfig:
    """Covers line 388-389 — ui_config not a dict."""

    def test_non_dict_ui_config_graceful(self):
        registry = ToolRegistry()
        # Pass ui as a non-dict (string) — should not raise
        app = create_app(config={"ui": "invalid_string"}, registry=registry)
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200


class TestAgentChatPaths:
    """Covers lines 626-662 — agent_runner None, agent raises, anomaly_score None."""

    def test_agent_chat_disabled_404(self):
        registry = ToolRegistry()
        app = create_app(
            config={"ui": {"agent_enabled": False, "enabled": False}},
            registry=registry,
        )
        client = TestClient(app)
        resp = client.post("/ui/agent/chat", json={"query": "hello"})
        assert resp.status_code == 404

    def test_agent_chat_runner_unavailable_503(self):
        """agent_enabled=True but agent fails to init → 503."""
        registry = ToolRegistry()
        with patch("agents.langgraph_agent.TricorderAgent.__init__", side_effect=RuntimeError("no llm")):
            app = create_app(
                config={"ui": {"agent_enabled": True, "enabled": False}},
                registry=registry,
            )
        client = TestClient(app)
        resp = client.post("/ui/agent/chat", json={"query": "hello"})
        assert resp.status_code == 503

    def test_agent_chat_agent_raises_500(self):
        """agent_runner.run() raises → 500."""
        registry = ToolRegistry()
        mock_agent = Mock()
        mock_agent.run.side_effect = RuntimeError("agent crash")
        mock_agent.build_graph.return_value = None

        with patch("agents.langgraph_agent.TricorderAgent", return_value=mock_agent):
            app = create_app(
                config={"ui": {"agent_enabled": True, "enabled": False}},
                registry=registry,
            )
        client = TestClient(app)
        resp = client.post("/ui/agent/chat", json={"query": "hello"})
        assert resp.status_code == 500


class TestServerExceptionClasses:
    """MCPServerError, ToolExecutionError, AuthenticationError hierarchy."""

    def test_hierarchy(self):
        assert issubclass(ToolExecutionError, MCPServerError)
        assert issubclass(AuthenticationError, MCPServerError)

    def test_raise_and_catch(self):
        with pytest.raises(MCPServerError):
            raise ToolExecutionError("tool failed")

    def test_auth_error_message(self):
        err = AuthenticationError("bad token")
        assert "bad token" in str(err)


class TestDefaultToolBootstrap:
    """Coverage for default tool bootstrap path when no registry is supplied."""

    def test_create_app_bootstraps_default_tools(self):
        app = create_app(config={"environment": "development", "ui": {"enabled": False}})
        client = TestClient(app)

        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["tools_registered"] >= 7

        tools_resp = client.get("/tools")
        assert tools_resp.status_code == 200
        names = {tool["name"] for tool in tools_resp.json()}
        assert {
            "read_sensor",
            "list_sensors",
            "read_all_sensors",
            "get_sensor_diagnostics",
            "calibrate_sensor",
            "run_anomaly_scan",
            "get_anomaly_history",
        }.issubset(names)

    def test_development_bootstrap_returns_simulated_readings(self):
        app = create_app(
            config={
                "environment": "development",
                "ui": {"enabled": False},
                "sensors": {
                    "i2c_devices": {
                        "bme680": {"enabled": True},
                    }
                },
            }
        )
        client = TestClient(app)

        resp = client.post(
            "/tools/call",
            json={"name": "read_all_sensors", "arguments": {}},
        )
        assert resp.status_code == 200
        readings = resp.json()["content"]
        assert "bme680" in readings
        assert readings["bme680"]["timestamp"] is not None
