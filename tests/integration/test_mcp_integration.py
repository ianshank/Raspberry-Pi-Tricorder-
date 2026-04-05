"""Integration tests for MCP server with sensor manager."""

import pytest
from unittest.mock import Mock
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from mcp_server.server import create_app, ToolRegistry
from mcp_server.tools.sensor_tools import register_sensor_tools
from sensors.base import SensorReading, SensorStatus
from sensors.manager import SensorManager


@pytest.mark.integration
class TestMCPWithSensors:
    @pytest.fixture
    def integrated_client(self, mock_i2c_adapter, bme680_config):
        """Full MCP server with real SensorManager and mocked I/O."""
        manager = SensorManager()
        manager.create_from_config("bme680", "int_bme680", mock_i2c_adapter, bme680_config)
        manager.initialize_all()

        registry = ToolRegistry()
        register_sensor_tools(registry, manager)

        app = create_app(config={}, registry=registry)
        return TestClient(app)

    def test_list_tools_has_sensor_tools(self, integrated_client):
        resp = integrated_client.get("/tools")
        assert resp.status_code == 200
        names = [t["name"] for t in resp.json()]
        assert "read_sensor" in names
        assert "list_sensors" in names

    def test_read_sensor_via_api(self, integrated_client):
        resp = integrated_client.post("/tools/call", json={
            "name": "read_sensor",
            "arguments": {"sensor_id": "int_bme680"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["isError"] is False
        assert data["content"]["sensor_id"] == "int_bme680"

    def test_list_sensors_via_api(self, integrated_client):
        resp = integrated_client.post("/tools/call", json={
            "name": "list_sensors",
            "arguments": {},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["content"]) == 1

    def test_read_nonexistent_sensor(self, integrated_client):
        resp = integrated_client.post("/tools/call", json={
            "name": "read_sensor",
            "arguments": {"sensor_id": "nonexistent"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data["content"]

    def test_diagnostics_via_api(self, integrated_client):
        resp = integrated_client.post("/tools/call", json={
            "name": "get_sensor_diagnostics",
            "arguments": {"sensor_id": "int_bme680"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"]["sensor_id"] == "int_bme680"

    def test_calibrate_via_api(self, integrated_client):
        resp = integrated_client.post("/tools/call", json={
            "name": "calibrate_sensor",
            "arguments": {"sensor_id": "int_bme680"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"]["calibration_success"] is True


@pytest.mark.integration
class TestMCPHealthWithSensors:
    def test_health_reports_tool_count(self, mock_i2c_adapter, bme680_config):
        manager = SensorManager()
        manager.create_from_config("bme680", "h_bme680", mock_i2c_adapter, bme680_config)
        manager.initialize_all()

        registry = ToolRegistry()
        register_sensor_tools(registry, manager)

        app = create_app(config={}, registry=registry)
        client = TestClient(app)

        resp = client.get("/health")
        data = resp.json()
        assert data["tools_registered"] == 5  # 5 sensor tools
