"""Unit tests for MCP sensor and anomaly tools."""

import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime, timezone

import numpy as np

from mcp_server.server import ToolRegistry
from mcp_server.tools.sensor_tools import register_sensor_tools
from mcp_server.tools.anomaly_tools import register_anomaly_tools
from sensors.base import SensorReading, SensorStatus
from sensors.manager import SensorManager
from models.base import ModelRegistry


class TestSensorTools:
    @pytest.fixture
    def sensor_setup(self):
        registry = ToolRegistry()
        manager = SensorManager()

        # Create mock sensor
        mock_sensor = Mock()
        mock_sensor.get_status.return_value = SensorStatus.READY
        mock_sensor.read.return_value = SensorReading(
            sensor_id="bme680_01",
            timestamp=datetime.now(timezone.utc),
            value={"temperature_c": 22.5},
            unit="composite",
            confidence=0.95,
        )
        mock_sensor.get_diagnostics.return_value = {
            "sensor_id": "bme680_01",
            "status": "ready",
            "total_reads": 10,
        }
        mock_sensor.calibrate.return_value = True
        manager.register_sensor("bme680_01", mock_sensor)

        register_sensor_tools(registry, manager)
        return registry, manager, mock_sensor

    def test_read_sensor_success(self, sensor_setup):
        registry, _, _ = sensor_setup
        result = registry._tools["read_sensor"](sensor_id="bme680_01")
        assert result["sensor_id"] == "bme680_01"
        assert "temperature_c" in result["value"]

    def test_read_sensor_not_found(self, sensor_setup):
        registry, _, _ = sensor_setup
        result = registry._tools["read_sensor"](sensor_id="nonexistent")
        assert "error" in result

    def test_list_sensors(self, sensor_setup):
        registry, _, _ = sensor_setup
        result = registry._tools["list_sensors"]()
        assert len(result) == 1
        assert result[0]["sensor_id"] == "bme680_01"

    def test_read_all_sensors(self, sensor_setup):
        registry, _, _ = sensor_setup
        result = registry._tools["read_all_sensors"]()
        assert "bme680_01" in result

    def test_get_diagnostics_specific(self, sensor_setup):
        registry, _, _ = sensor_setup
        result = registry._tools["get_sensor_diagnostics"](sensor_id="bme680_01")
        assert result["sensor_id"] == "bme680_01"
        assert result["total_reads"] == 10

    def test_get_diagnostics_all(self, sensor_setup):
        registry, _, _ = sensor_setup
        result = registry._tools["get_sensor_diagnostics"]()
        assert "bme680_01" in result

    def test_get_diagnostics_not_found(self, sensor_setup):
        registry, _, _ = sensor_setup
        result = registry._tools["get_sensor_diagnostics"](sensor_id="nope")
        assert "error" in result

    def test_calibrate_success(self, sensor_setup):
        registry, _, _ = sensor_setup
        result = registry._tools["calibrate_sensor"](sensor_id="bme680_01")
        assert result["calibration_success"] is True

    def test_calibrate_not_found(self, sensor_setup):
        registry, _, _ = sensor_setup
        result = registry._tools["calibrate_sensor"](sensor_id="nope")
        assert "error" in result

    def test_read_sensor_error(self, sensor_setup):
        registry, _, mock_sensor = sensor_setup
        mock_sensor.read.side_effect = RuntimeError("fail")
        result = registry._tools["read_sensor"](sensor_id="bme680_01")
        assert "error" in result

    def test_tools_registered(self, sensor_setup):
        registry, _, _ = sensor_setup
        expected = ["read_sensor", "list_sensors", "read_all_sensors",
                     "get_sensor_diagnostics", "calibrate_sensor"]
        for name in expected:
            assert registry.has_tool(name)


class TestAnomalyTools:
    @pytest.fixture
    def anomaly_setup(self):
        registry = ToolRegistry()

        # Create and register mock anomaly model
        mock_model = Mock()
        mock_model.config = {"input_shape": [1, 4, 2]}
        mock_model.predict.return_value = Mock(
            to_dict=Mock(return_value={
                "output": {"anomaly_score": 0.3, "is_anomaly": False},
                "confidence": 0.7,
            })
        )
        mock_model.get_anomaly_history = Mock(return_value=[
            {"anomaly_score": 0.1}, {"anomaly_score": 0.2}
        ])

        # Patch ModelRegistry
        orig_get = ModelRegistry.get
        ModelRegistry.get = Mock(side_effect=lambda mid: mock_model if mid == "anomaly_detector" else None)

        register_anomaly_tools(registry)

        yield registry, mock_model

        ModelRegistry.get = orig_get

    def test_run_anomaly_scan(self, anomaly_setup):
        registry, _ = anomaly_setup
        result = registry._tools["run_anomaly_scan"](model_id="anomaly_detector")
        assert "output" in result

    def test_run_anomaly_scan_with_data(self, anomaly_setup):
        registry, _ = anomaly_setup
        result = registry._tools["run_anomaly_scan"](
            model_id="anomaly_detector",
            sensor_data=[[[1.0, 2.0], [3.0, 4.0], [5.0, 6.0], [7.0, 8.0]]],
        )
        assert "output" in result

    def test_run_anomaly_model_not_found(self, anomaly_setup):
        registry, _ = anomaly_setup
        result = registry._tools["run_anomaly_scan"](model_id="nonexistent")
        assert "error" in result

    def test_get_anomaly_history(self, anomaly_setup):
        registry, _ = anomaly_setup
        result = registry._tools["get_anomaly_history"](model_id="anomaly_detector")
        assert result["count"] == 2

    def test_get_anomaly_history_not_found(self, anomaly_setup):
        registry, _ = anomaly_setup
        result = registry._tools["get_anomaly_history"](model_id="nonexistent")
        assert "error" in result

    def test_tools_registered(self, anomaly_setup):
        registry, _ = anomaly_setup
        assert registry.has_tool("run_anomaly_scan")
        assert registry.has_tool("get_anomaly_history")
