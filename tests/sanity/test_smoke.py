"""Sanity/smoke tests for basic functionality."""

import pytest

from agents.langgraph_agent import TricorderAgent
from mcp_server.server import create_app
from sensors.base import SensorFactory
from sensors.manager import SensorManager
from utils.config import TricorderConfig, load_config


@pytest.mark.sanity
class TestSmokeTests:
    def test_config_loads_defaults(self):
        """Config loads without errors using defaults."""
        config = TricorderConfig()
        assert config.project_name is not None
        assert config.version is not None

    def test_config_loads_from_file(self, test_config_path):
        """Config loads from YAML file."""
        config = load_config(test_config_path)
        assert config.project_name == "Test Tricorder"

    def test_sensor_factory_has_types(self):
        """SensorFactory has registered sensor types."""
        types = SensorFactory.list_types()
        assert len(types) >= 7

    def test_sensor_create_and_init(self, mock_i2c_adapter, bme680_config):
        """Can create and initialize a sensor."""
        sensor = SensorFactory.create("bme680", "smoke_bme", mock_i2c_adapter, bme680_config)
        assert sensor.initialize() is True

    def test_sensor_read(self, mock_i2c_adapter, bme680_config):
        """Can read from an initialized sensor."""
        sensor = SensorFactory.create("bme680", "smoke_read", mock_i2c_adapter, bme680_config)
        sensor.initialize()
        reading = sensor.read()
        assert reading.value is not None

    def test_mcp_server_starts(self):
        """MCP server app creates without errors."""
        app = create_app(config={})
        assert app is not None

    def test_mcp_health_endpoint(self):
        """Health endpoint responds."""
        from fastapi.testclient import TestClient
        app = create_app(config={})
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_agent_creates(self, agent_config):
        """Agent creates without errors."""
        agent = TricorderAgent(config=agent_config)
        assert agent is not None

    def test_agent_runs(self, agent_config):
        """Agent can process an event."""
        agent = TricorderAgent(config=agent_config)
        result = agent.run({"anomaly_score": 0.5})
        assert result["report"] is not None

    def test_sensor_manager_creates(self):
        """SensorManager creates without errors."""
        manager = SensorManager()
        assert manager.sensor_count == 0
