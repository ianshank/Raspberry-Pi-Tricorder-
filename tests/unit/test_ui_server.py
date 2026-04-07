"""Unit tests for UI-serving and websocket behavior in MCP server."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from mcp_server.server import ToolRegistry, create_app


@pytest.fixture
def sensor_registry():
    registry = ToolRegistry()

    @registry.register(
        name="read_all_sensors",
        description="Read all sensors",
        input_schema={"type": "object", "properties": {}},
    )
    def read_all_sensors():
        return {
            "bme680": {
                "sensor_id": "bme680",
                "value": {"temperature_c": 23.4},
                "confidence": 0.98,
            }
        }

    @registry.register(
        name="run_anomaly_scan",
        description="Run anomaly scan",
        input_schema={"type": "object", "properties": {"model_id": {"type": "string"}}},
    )
    def run_anomaly_scan(model_id: str = "anomaly_detector"):
        return {
            "model_id": model_id,
            "output": {
                "anomaly_score": 0.86,
                "is_anomaly": True,
            },
            "confidence": 0.91,
        }

    @registry.register(
        name="get_anomaly_history",
        description="Get anomaly history",
        input_schema={"type": "object", "properties": {}},
    )
    def get_anomaly_history(model_id: str = "anomaly_detector", limit: int = 1):
        entries = [
            {
                "timestamp": "2026-04-05T00:00:00Z",
                "anomaly_score": 0.84,
                "is_anomaly": True,
            }
        ]
        return {
            "model_id": model_id,
            "entries": entries[:limit],
            "count": min(limit, len(entries)),
        }

    @registry.register(
        name="read_sensor",
        description="Read one sensor",
        input_schema={"type": "object", "properties": {"sensor_id": {"type": "string"}}},
    )
    def read_sensor(sensor_id: str):
        return {"sensor_id": sensor_id, "value": {"status": "ok"}}

    @registry.register(
        name="get_sensor_diagnostics",
        description="Get sensor diagnostics",
        input_schema={"type": "object", "properties": {}},
    )
    def get_sensor_diagnostics(sensor_id: str = ""):
        return {"sensor_id": sensor_id or "all", "status": "ready"}

    return registry


@pytest.fixture
def ui_client(sensor_registry):
    app = create_app(
        config={
            "ui": {
                "enabled": True,
                "static_dir": "src/ui/static",
                "poll_interval_ms": 100,
                "ws_path": "/ws/sensors",
                "anomaly_ws_path": "/ws/anomalies",
                "anomaly_poll_interval_ms": 100,
                "anomaly_model_id": "anomaly_detector",
                "anomaly_history_limit": 1,
                "anomaly_ack_enabled": True,
                "anomaly_ack_path": "/ui/anomalies/ack",
                "anomaly_ack_history_limit": 200,
                "anomaly_alert_threshold": 0.75,
                "agent_enabled": True,
                "agent_chat_path": "/ui/agent/chat",
                "reconnect_initial_ms": 700,
                "reconnect_max_ms": 5000,
                "theme": "classic",
                "debug": False,
                "panel_order": ["env"],
                "panels": {
                    "env": {
                        "label": "ENV",
                        "sensors": ["bme680"],
                        "color": "golden-tanoi",
                    }
                },
            }
        },
        registry=sensor_registry,
    )
    return TestClient(app)


class TestUIServerRoutes:
    def test_ui_config_endpoint(self, ui_client):
        resp = ui_client.get("/ui/config.json")
        assert resp.status_code == 200
        data = resp.json()
        assert "project_name" in data
        assert "version" in data
        assert data["enabled"] is True
        assert data["theme"] == "classic"
        assert data["ws_path"] == "/ws/sensors"
        assert data["anomaly_ws_path"] == "/ws/anomalies"
        assert data["anomaly_ack_enabled"] is True
        assert data["anomaly_ack_path"] == "/ui/anomalies/ack"
        assert data["anomaly_ack_history_limit"] == 200
        assert data["agent_chat_path"] == "/ui/agent/chat"
        assert data["anomaly_model_id"] == "anomaly_detector"
        assert data["agent_enabled"] is True
        assert data["reconnect_initial_ms"] == 700
        assert data["reconnect_max_ms"] == 5000
        assert data["panel_order"] == ["env"]
        assert "env" in data["panels"]
        assert "bme680" in data["sensor_catalog"]
        assert "label" in data["sensor_catalog"]["bme680"]

    def test_ui_static_index_served(self, ui_client):
        resp = ui_client.get("/ui/index.html")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_root_redirects_to_ui(self, ui_client):
        resp = ui_client.get("/", follow_redirects=False)
        assert resp.status_code in {302, 307}
        assert resp.headers["location"] == "/ui/index.html"

    def test_ui_config_uses_sensor_labels_from_backend(self, sensor_registry):
        app = create_app(
            config={
                "sensors": {
                    "i2c_devices": {
                        "bme680": {
                            "label": "AIR QUALITY SENSOR",
                        },
                    },
                },
                "ui": {
                    "enabled": True,
                    "static_dir": "src/ui/static",
                    "poll_interval_ms": 100,
                    "panels": {
                        "env": {
                            "label": "ENV",
                            "sensors": ["bme680"],
                            "color": "golden-tanoi",
                        },
                    },
                },
            },
            registry=sensor_registry,
        )
        client = TestClient(app)
        resp = client.get("/ui/config.json")
        assert resp.status_code == 200
        data = resp.json()
        assert data["sensor_catalog"]["bme680"]["label"] == "AIR QUALITY SENSOR"

    def test_ui_disabled_when_static_dir_missing(self, sensor_registry):
        app = create_app(
            config={
                "ui": {
                    "enabled": True,
                    "static_dir": "src/ui/does-not-exist",
                }
            },
            registry=sensor_registry,
        )
        client = TestClient(app)

        cfg = client.get("/ui/config.json")
        assert cfg.status_code == 200
        assert cfg.json()["enabled"] is False

        root = client.get("/", follow_redirects=False)
        assert root.status_code == 404

    def test_ui_panel_order_falls_back_to_declared_panels(self, sensor_registry):
        app = create_app(
            config={
                "ui": {
                    "enabled": True,
                    "static_dir": "src/ui/static",
                    "panel_order": ["missing"],
                    "panels": {
                        "env": {
                            "label": "ENV",
                            "sensors": ["bme680"],
                            "color": "golden-tanoi",
                        },
                        "bio": {
                            "label": "BIO",
                            "sensors": ["max30102"],
                            "color": "anakiwa",
                        },
                    },
                }
            },
            registry=sensor_registry,
        )
        client = TestClient(app)

        resp = client.get("/ui/config.json")
        assert resp.status_code == 200
        assert resp.json()["panel_order"] == ["env", "bio"]

    def test_ui_config_adds_unknown_panel_sensor_to_catalog(self, sensor_registry):
        app = create_app(
            config={
                "ui": {
                    "enabled": True,
                    "static_dir": "src/ui/static",
                    "panels": {
                        "env": {
                            "label": "ENV",
                            "sensors": ["unknown-sensor_01"],
                            "color": "golden-tanoi",
                        },
                    },
                }
            },
            registry=sensor_registry,
        )
        client = TestClient(app)

        resp = client.get("/ui/config.json")
        assert resp.status_code == 200
        sensor = resp.json()["sensor_catalog"]["unknown-sensor_01"]
        assert sensor["label"] == "UNKNOWN SENSOR 01"
        assert sensor["source"] == "unknown"


class TestSensorStream:
    def test_sensor_stream_payload(self, ui_client):
        with ui_client.websocket_connect("/ws/sensors") as ws:
            payload = ws.receive_json()
        assert "timestamp" in payload
        assert "readings" in payload
        assert "bme680" in payload["readings"]

    def test_sensor_stream_auth_enforced(self, sensor_registry):
        app = create_app(
            config={
                "auth_enabled": True,
                "api_key": "secret",
                "ui": {
                    "enabled": True,
                    "static_dir": "src/ui/static",
                    "poll_interval_ms": 100,
                },
            },
            registry=sensor_registry,
        )
        client = TestClient(app)

        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/sensors"):
                pass

    def test_sensor_stream_auth_enabled_without_key_disconnects(self, sensor_registry):
        app = create_app(
            config={
                "auth_enabled": True,
                "ui": {
                    "enabled": True,
                    "static_dir": "src/ui/static",
                    "poll_interval_ms": 100,
                },
            },
            registry=sensor_registry,
        )
        client = TestClient(app)

        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/sensors"):
                pass

    def test_sensor_stream_auth_accepts_token(self, sensor_registry):
        app = create_app(
            config={
                "auth_enabled": True,
                "api_key": "secret",
                "ui": {
                    "enabled": True,
                    "static_dir": "src/ui/static",
                    "poll_interval_ms": 100,
                },
            },
            registry=sensor_registry,
        )
        client = TestClient(app)

        with client.websocket_connect("/ws/sensors?token=secret") as ws:
            payload = ws.receive_json()
        assert "readings" in payload

    def test_sensor_stream_auth_accepts_api_key_query_param(self, sensor_registry):
        app = create_app(
            config={
                "auth_enabled": True,
                "api_key": "secret",
                "ui": {
                    "enabled": True,
                    "static_dir": "src/ui/static",
                    "poll_interval_ms": 100,
                },
            },
            registry=sensor_registry,
        )
        client = TestClient(app)

        with client.websocket_connect("/ws/sensors?api_key=secret") as ws:
            payload = ws.receive_json()
        assert "readings" in payload

    def test_sensor_stream_custom_ws_path(self, sensor_registry):
        app = create_app(
            config={
                "ui": {
                    "enabled": True,
                    "static_dir": "src/ui/static",
                    "poll_interval_ms": 100,
                    "ws_path": "/ws/custom-sensors",
                },
            },
            registry=sensor_registry,
        )
        client = TestClient(app)

        with client.websocket_connect("/ws/custom-sensors") as ws:
            payload = ws.receive_json()
        assert "readings" in payload

    def test_sensor_stream_invalid_path_falls_back_to_default_route(self, sensor_registry):
        app = create_app(
            config={
                "ui": {
                    "enabled": True,
                    "static_dir": "src/ui/static",
                    "poll_interval_ms": 100,
                    "ws_path": "invalid-path",
                },
            },
            registry=sensor_registry,
        )
        client = TestClient(app)

        with client.websocket_connect("/ws/sensors") as ws:
            payload = ws.receive_json()
        assert "readings" in payload


class TestAnomalyStream:
    def test_anomaly_stream_payload(self, ui_client):
        with ui_client.websocket_connect("/ws/anomalies") as ws:
            payload = ws.receive_json()
        assert "timestamp" in payload
        assert payload["model_id"] == "anomaly_detector"
        assert "anomaly_id" in payload
        assert "anomaly_score" in payload
        assert "is_anomaly" in payload
        assert "severity" in payload
        assert payload["acknowledged"] is False

    def test_anomaly_stream_custom_ws_path(self, sensor_registry):
        app = create_app(
            config={
                "ui": {
                    "enabled": True,
                    "static_dir": "src/ui/static",
                    "poll_interval_ms": 100,
                    "anomaly_poll_interval_ms": 100,
                    "anomaly_ws_path": "/ws/custom-anomalies",
                },
            },
            registry=sensor_registry,
        )
        client = TestClient(app)

        with client.websocket_connect("/ws/custom-anomalies") as ws:
            payload = ws.receive_json()
        assert "anomaly_score" in payload

    def test_anomaly_stream_infers_anomaly_flag_from_threshold(self):
        registry = ToolRegistry()

        @registry.register(
            name="run_anomaly_scan",
            description="Run anomaly scan",
            input_schema={"type": "object", "properties": {"model_id": {"type": "string"}}},
        )
        def run_anomaly_scan(model_id: str = "anomaly_detector"):
            return {
                "model_id": model_id,
                "output": {
                    "anomaly_score": 0.80,
                },
            }

        app = create_app(
            config={
                "ui": {
                    "enabled": True,
                    "static_dir": "src/ui/static",
                    "anomaly_poll_interval_ms": 100,
                    "anomaly_alert_threshold": 0.75,
                },
            },
            registry=registry,
        )
        client = TestClient(app)

        with client.websocket_connect("/ws/anomalies") as ws:
            payload = ws.receive_json()
        assert payload["anomaly_score"] == pytest.approx(0.80)
        assert payload["is_anomaly"] is True
        assert payload["severity"] == "HIGH"

    def test_anomaly_stream_uses_history_when_scan_missing(self):
        registry = ToolRegistry()

        @registry.register(
            name="get_anomaly_history",
            description="Get anomaly history",
            input_schema={"type": "object", "properties": {}},
        )
        def get_anomaly_history(model_id: str = "anomaly_detector", limit: int = 1):
            entries = [
                {
                    "timestamp": "2026-04-05T00:00:00Z",
                    "anomaly_score": 0.42,
                    "is_anomaly": True,
                    "confidence": 0.88,
                }
            ]
            return {
                "model_id": model_id,
                "entries": entries[:limit],
                "count": min(limit, len(entries)),
            }

        app = create_app(
            config={
                "ui": {
                    "enabled": True,
                    "static_dir": "src/ui/static",
                    "anomaly_poll_interval_ms": 100,
                    "anomaly_history_limit": 1,
                },
            },
            registry=registry,
        )
        client = TestClient(app)

        with client.websocket_connect("/ws/anomalies") as ws:
            payload = ws.receive_json()
        assert payload["anomaly_score"] == pytest.approx(0.42)
        assert payload["is_anomaly"] is False
        assert payload["confidence"] == pytest.approx(0.88)
        assert payload["severity"] == "LOW"
        assert len(payload["history"]) == 1


class TestAgentChat:
    def test_agent_chat_endpoint(self, ui_client):
        resp = ui_client.post(
            "/ui/agent/chat",
            json={
                "query": "What is the current anomaly state?",
                "include_sensor_context": True,
            },
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["query"] == "What is the current anomaly state?"
        assert "reply" in payload
        assert "report" in payload
        assert "severity" in payload
        assert "context" in payload

    def test_agent_chat_disabled(self, sensor_registry):
        app = create_app(
            config={
                "ui": {
                    "enabled": True,
                    "static_dir": "src/ui/static",
                    "agent_enabled": False,
                },
            },
            registry=sensor_registry,
        )
        client = TestClient(app)
        resp = client.post(
            "/ui/agent/chat",
            json={"query": "status", "include_sensor_context": False},
        )
        assert resp.status_code == 404

    def test_agent_chat_custom_path(self, sensor_registry):
        app = create_app(
            config={
                "ui": {
                    "enabled": True,
                    "static_dir": "src/ui/static",
                    "agent_enabled": True,
                    "agent_chat_path": "/ui/chat/custom",
                },
            },
            registry=sensor_registry,
        )
        client = TestClient(app)
        resp = client.post(
            "/ui/chat/custom",
            json={"query": "status", "include_sensor_context": False},
        )
        assert resp.status_code == 200

    def test_agent_chat_excludes_sensor_context_when_disabled(self, ui_client):
        resp = ui_client.post(
            "/ui/agent/chat",
            json={
                "query": "status",
                "include_sensor_context": False,
            },
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["context"]["sensors"] == []

    def test_agent_chat_rejects_empty_query(self, ui_client):
        resp = ui_client.post(
            "/ui/agent/chat",
            json={
                "query": "",
                "include_sensor_context": False,
            },
        )
        assert resp.status_code == 422


class TestAnomalyAcknowledgment:
    def test_ack_endpoint_marks_anomaly_as_acknowledged(self, ui_client):
        with ui_client.websocket_connect("/ws/anomalies") as ws:
            payload = ws.receive_json()

        anomaly_id = payload["anomaly_id"]
        assert payload["acknowledged"] is False

        ack_resp = ui_client.post(
            "/ui/anomalies/ack",
            json={
                "anomaly_id": anomaly_id,
                "acknowledged_by": "tests",
                "note": "Operator acknowledged",
            },
        )
        assert ack_resp.status_code == 200
        ack_payload = ack_resp.json()
        assert ack_payload["ok"] is True
        assert ack_payload["acknowledgment"]["anomaly_id"] == anomaly_id
        assert ack_payload["acknowledgment"]["acknowledged_by"] == "tests"

        with ui_client.websocket_connect("/ws/anomalies") as ws:
            payload_after_ack = ws.receive_json()
        assert payload_after_ack["anomaly_id"] == anomaly_id
        assert payload_after_ack["acknowledged"] is True
        assert payload_after_ack["acknowledgment"]["anomaly_id"] == anomaly_id

    def test_ack_endpoint_disabled(self, sensor_registry):
        app = create_app(
            config={
                "ui": {
                    "enabled": True,
                    "static_dir": "src/ui/static",
                    "anomaly_ack_enabled": False,
                },
            },
            registry=sensor_registry,
        )
        client = TestClient(app)
        resp = client.post(
            "/ui/anomalies/ack",
            json={"anomaly_id": "anom-test"},
        )
        assert resp.status_code == 404

    def test_ack_endpoint_custom_path(self, sensor_registry):
        app = create_app(
            config={
                "ui": {
                    "enabled": True,
                    "static_dir": "src/ui/static",
                    "anomaly_ack_enabled": True,
                    "anomaly_ack_path": "/ui/anomaly/confirm",
                },
            },
            registry=sensor_registry,
        )
        client = TestClient(app)
        resp = client.post(
            "/ui/anomaly/confirm",
            json={"anomaly_id": "anom-test", "acknowledged_by": "qa"},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_ack_endpoint_rejects_blank_anomaly_id(self, ui_client):
        resp = ui_client.post(
            "/ui/anomalies/ack",
            json={"anomaly_id": "   "},
        )
        assert resp.status_code == 400


class TestAnomalyHistory:
    """Tests for the anomaly history pagination endpoint (F4)."""

    @pytest.fixture
    def history_client(self, sensor_registry):
        app = create_app(config={"ui": {
            "enabled": True, "static_dir": "src/ui/static",
            "anomaly_ack_enabled": True, "anomaly_ack_db_path": "",
            "anomaly_history_path": "/ui/anomalies/history",
            "anomaly_history_page_size": 50,
        }}, registry=sensor_registry)
        return TestClient(app)

    def test_history_empty(self, history_client):
        resp = history_client.get("/ui/anomalies/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["total_pages"] == 1

    def test_history_returns_acked_items(self, history_client):
        history_client.post("/ui/anomalies/ack", json={"anomaly_id": "h-001"})
        history_client.post("/ui/anomalies/ack", json={"anomaly_id": "h-002"})
        resp = history_client.get("/ui/anomalies/history")
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    def test_history_pagination(self, history_client):
        for i in range(5):
            history_client.post("/ui/anomalies/ack", json={"anomaly_id": f"h-{i:03d}"})
        resp = history_client.get("/ui/anomalies/history?page=1&page_size=2")
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5
        assert data["total_pages"] == 3

    def test_history_filter_by_operator(self, history_client):
        history_client.post(
            "/ui/anomalies/ack",
            json={"anomaly_id": "h-001", "acknowledged_by": "kirk"},
        )
        history_client.post(
            "/ui/anomalies/ack",
            json={"anomaly_id": "h-002", "acknowledged_by": "spock"},
        )
        resp = history_client.get("/ui/anomalies/history?acknowledged_by=kirk")
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["acknowledged_by"] == "kirk"


class TestOperatorIdentity:
    """Tests for operator identity propagation (F3)."""

    @pytest.fixture
    def auth_client(self, sensor_registry):
        app = create_app(config={
            "mcp_server": {
                "auth_enabled": True, "api_key": "secret123",
                "operator_map": {"secret123": "operator-kirk"},
            },
            "ui": {
                "enabled": True, "static_dir": "src/ui/static",
                "anomaly_ack_enabled": True, "anomaly_ack_db_path": "",
            },
        }, registry=sensor_registry)
        return TestClient(app)

    @pytest.fixture
    def noauth_client(self, sensor_registry):
        app = create_app(config={"ui": {
            "enabled": True, "static_dir": "src/ui/static",
            "anomaly_ack_enabled": True, "anomaly_ack_db_path": "",
        }}, registry=sensor_registry)
        return TestClient(app)

    def test_anonymous_operator_default(self, noauth_client):
        resp = noauth_client.post(
            "/ui/anomalies/ack", json={"anomaly_id": "op-001"},
        )
        assert resp.status_code == 200
        record = resp.json()["acknowledgment"]
        assert record["acknowledged_by"] == "ui"
        assert record["operator_source"] == "anonymous"

    def test_operator_from_bearer_token(self, auth_client):
        resp = auth_client.post(
            "/ui/anomalies/ack",
            json={"anomaly_id": "op-002"},
            headers={"Authorization": "Bearer secret123"},
        )
        assert resp.status_code == 200
        record = resp.json()["acknowledgment"]
        assert record["acknowledged_by"] == "operator-kirk"
        assert record["operator_source"] == "bearer_token"

    def test_explicit_acknowledged_by_overrides_operator(self, auth_client):
        resp = auth_client.post(
            "/ui/anomalies/ack",
            json={"anomaly_id": "op-003", "acknowledged_by": "spock"},
            headers={"Authorization": "Bearer secret123"},
        )
        assert resp.status_code == 200
        record = resp.json()["acknowledgment"]
        assert record["acknowledged_by"] == "spock"
