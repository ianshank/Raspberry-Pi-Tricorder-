"""Tests for health and metrics endpoints."""

import time

import pytest

from mcp_server.health import build_basic_health, build_detailed_health


class TestBuildBasicHealth:
    """Basic liveness response maintains backwards-compatible shape."""

    def test_basic_health_shape(self):
        result = build_basic_health(tools_registered=7)
        assert result["status"] == "healthy"
        assert "timestamp" in result
        assert result["tools_registered"] == 7

    def test_basic_health_keys_exact(self):
        result = build_basic_health(tools_registered=0)
        assert set(result.keys()) == {"status", "timestamp", "tools_registered"}


class TestBuildDetailedHealth:
    """Detailed health with per-sensor status and derived overall state."""

    @pytest.fixture
    def start_time(self):
        return time.monotonic() - 60.0  # 60 seconds ago

    def test_healthy_when_all_sensors_ready(self, start_time):
        sensor_health = {
            "bme680": {"status": "ready", "type": "BME680", "error_count": 0},
            "mlx90640": {"status": "reading", "type": "MLX90640", "error_count": 0},
        }
        result = build_detailed_health(
            version="1.0.0",
            start_time=start_time,
            tools_registered=7,
            sensor_health=sensor_health,
            mqtt_connected=True,
            mqtt_messages_published=42,
        )
        assert result["status"] == "healthy"
        assert result["version"] == "1.0.0"
        assert result["uptime_s"] >= 59.0
        assert result["tools_registered"] == 7
        assert result["sensors"] == sensor_health
        assert result["mqtt"]["connected"] is True
        assert result["mqtt"]["messages_published"] == 42

    def test_degraded_when_some_sensors_errored(self, start_time):
        sensor_health = {
            "bme680": {"status": "ready", "type": "BME680", "error_count": 0},
            "ads1263": {"status": "error", "type": "ADS1263", "error_count": 3},
        }
        result = build_detailed_health(
            version="1.0.0",
            start_time=start_time,
            tools_registered=5,
            sensor_health=sensor_health,
            mqtt_connected=False,
        )
        assert result["status"] == "degraded"

    def test_unhealthy_when_no_sensors_ready(self, start_time):
        sensor_health = {
            "bme680": {"status": "error", "type": "BME680", "error_count": 5},
            "ads1263": {"status": "uninitialized", "type": "ADS1263", "error_count": 0},
        }
        result = build_detailed_health(
            version="1.0.0",
            start_time=start_time,
            tools_registered=3,
            sensor_health=sensor_health,
            mqtt_connected=False,
        )
        assert result["status"] == "unhealthy"

    def test_healthy_when_no_sensors_registered(self, start_time):
        result = build_detailed_health(
            version="1.0.0",
            start_time=start_time,
            tools_registered=0,
            sensor_health={},
            mqtt_connected=False,
        )
        assert result["status"] == "healthy"

    def test_response_contains_timestamp(self, start_time):
        result = build_detailed_health(
            version="2.0.0",
            start_time=start_time,
            tools_registered=0,
            sensor_health={},
            mqtt_connected=False,
        )
        assert "timestamp" in result

    def test_mqtt_defaults(self, start_time):
        result = build_detailed_health(
            version="1.0.0",
            start_time=start_time,
            tools_registered=0,
            sensor_health={},
            mqtt_connected=False,
        )
        assert result["mqtt"]["messages_published"] == 0
