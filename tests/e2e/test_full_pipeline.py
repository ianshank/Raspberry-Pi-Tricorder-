"""End-to-end tests for the full Tricorder pipeline."""

import pytest

import numpy as np

from utils.config import load_config
from sensors.manager import SensorManager
from models.base import ModelRegistry
from models.anomaly_detector import AnomalyDetector
from mcp_server.server import ToolRegistry
from mcp_server.tools.sensor_tools import register_sensor_tools
from mcp_server.tools.anomaly_tools import register_anomaly_tools
from agents.langgraph_agent import TricorderAgent


@pytest.mark.e2e
class TestFullPipeline:
    @pytest.fixture
    def full_setup(self, mock_i2c_adapter, mock_spi_adapter, mock_inference_adapter, test_config_path):
        """Set up complete pipeline: config -> sensors -> models -> MCP -> agent."""
        config = load_config(test_config_path)

        # Set up sensors
        sensor_manager = SensorManager()
        sensor_manager.create_from_config(
            "bme680", "e2e_bme680", mock_i2c_adapter,
            {"address": 0x76}
        )
        sensor_manager.create_from_config(
            "ads1263", "e2e_adc", mock_spi_adapter,
            {"bus": 0, "device": 0, "channels": {"ch1": {"positive_input": 0, "negative_input": 1}}}
        )
        sensor_manager.initialize_all()

        # Set up models
        orig_instances = ModelRegistry._instances.copy()
        model = AnomalyDetector(
            "e2e_anomaly", mock_inference_adapter,
            {"model_path": "test.onnx", "input_shape": [1, 256, 10], "output_shape": [1, 10],
             "confidence_threshold": 0.75, "window_size": 256}
        )
        model.load()
        ModelRegistry._instances["anomaly_detector"] = model

        # Set up MCP
        registry = ToolRegistry()
        register_sensor_tools(registry, sensor_manager)
        register_anomaly_tools(registry)

        # Set up agent with tool caller
        def tool_caller(name, args):
            import asyncio
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(registry.call(name, args))
            finally:
                loop.close()

        agent = TricorderAgent(
            config=config.agent.model_dump(),
            tool_caller=tool_caller,
        )

        yield {
            "config": config,
            "sensor_manager": sensor_manager,
            "model": model,
            "registry": registry,
            "agent": agent,
        }

        ModelRegistry._instances = orig_instances

    def test_config_to_sensors_to_read(self, full_setup):
        """Config loads -> sensors initialize -> readings produced."""
        manager = full_setup["sensor_manager"]
        readings = manager.read_all()
        assert len(readings) == 2
        for reading in readings.values():
            assert reading is not None
            d = reading.to_dict()
            assert "sensor_id" in d
            assert "value" in d

    def test_sensor_to_anomaly_detection(self, full_setup):
        """Sensor data flows into anomaly detector."""
        model = full_setup["model"]
        input_data = np.random.randn(1, 256, 10).astype(np.float32)
        result = model.predict(input_data)
        assert "anomaly_score" in result.output
        assert "is_anomaly" in result.output

    def test_agent_full_cycle(self, full_setup):
        """Agent receives event -> gathers evidence -> produces report."""
        agent = full_setup["agent"]
        result = agent.run({
            "anomaly_score": 0.82,
            "affected_sensors": ["e2e_bme680"],
        })
        assert result["report"] is not None
        assert result["severity"] == "HIGH"
        assert "Tricorder Situation Report" in result["report"]

    def test_mcp_tools_accessible(self, full_setup):
        """All tools are accessible via registry."""
        registry = full_setup["registry"]
        tools = registry.list_tools()
        tool_names = [t.name for t in tools]
        assert "read_sensor" in tool_names
        assert "list_sensors" in tool_names
        assert "run_anomaly_scan" in tool_names
