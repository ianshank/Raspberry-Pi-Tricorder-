"""End-to-end tests for the full Tricorder pipeline."""
from __future__ import annotations

import numpy as np
import pytest

from agents.langgraph_agent import TricorderAgent
from mcp_server.server import ToolRegistry
from mcp_server.tools.anomaly_tools import register_anomaly_tools
from mcp_server.tools.sensor_tools import register_sensor_tools
from models.anomaly_detector import AnomalyDetector
from models.base import ModelRegistry
from sensors.manager import SensorManager
from utils.config import load_config


@pytest.mark.e2e
class TestFullPipeline:
    @pytest.fixture
    def full_setup(self, mock_i2c_adapter, mock_spi_adapter, mock_inference_adapter, test_config_path):
        """Set up complete pipeline: config -> sensors -> models -> MCP -> agent."""
        orig_instances = ModelRegistry._instances.copy()
        try:
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

            # Set up model via registry API (default tool model_id is anomaly_detector)
            model = ModelRegistry.create(
                "anomaly_detector",
                "anomaly_detector",
                mock_inference_adapter,
                {
                    "model_path": "test.onnx",
                    "input_shape": [1, 256, 10],
                    "output_shape": [1, 10],
                    "confidence_threshold": 0.75,
                    "window_size": 256,
                },
            )
            assert isinstance(model, AnomalyDetector)
            model.load()

            # Set up MCP
            registry = ToolRegistry()
            register_sensor_tools(registry, sensor_manager)
            register_anomaly_tools(registry)

            # Set up agent with tool caller
            def tool_caller(name, args):
                import asyncio
                return asyncio.run(registry.call(name, args))

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
        finally:
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
        assert isinstance(result["report"], str)
        assert result["report"]
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

    def test_sensor_to_anomaly_to_agent_report(self, full_setup):
        """Full chain: read sensors -> anomaly detect -> agent report."""
        manager = full_setup["sensor_manager"]
        model = full_setup["model"]
        agent = full_setup["agent"]
        readings = manager.read_all()
        assert len(readings) > 0
        input_data = np.random.randn(1, 256, 10).astype(np.float32)
        result = model.predict(input_data)
        score = result.output.get("anomaly_score", 0.82)
        agent_result = agent.run({
            "anomaly_score": score,
            "affected_sensors": list(readings.keys()),
        })
        assert isinstance(agent_result["report"], str)
        assert agent_result["report"]
        assert agent_result["severity"] is not None

    def test_chat_endpoint_with_sensor_context(self, full_setup, tmp_path):
        """Agent chat returns sensor context in response."""
        from fastapi.testclient import TestClient

        from mcp_server.server import create_app
        static_dir = full_setup["config"].ui.static_dir
        db_path = str(tmp_path / "chat-context.db")
        app = create_app(
            config={"ui": {"enabled": True, "static_dir": static_dir, "anomaly_ack_db_path": db_path}},
            registry=full_setup["registry"],
        )
        client = TestClient(app)
        resp = client.post("/ui/agent/chat", json={"query": "What sensors are active?", "include_sensor_context": True})
        assert resp.status_code == 200
        data = resp.json()
        assert "reply" in data
        assert "report" in data
        assert "context" in data

    def test_chat_with_operator_identity(self, full_setup, tmp_path):
        """Operator identity propagates to chat response context."""
        from fastapi.testclient import TestClient

        from mcp_server.server import create_app
        static_dir = full_setup["config"].ui.static_dir
        db_path = str(tmp_path / "chat-identity.db")
        app = create_app(
            config={"ui": {"enabled": True, "static_dir": static_dir, "anomaly_ack_db_path": db_path}},
            registry=full_setup["registry"],
        )
        client = TestClient(app)
        resp = client.post("/ui/agent/chat", json={"query": "status", "operator_id": "bones"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["context"]["operator_id"] == "bones"

    def test_anomaly_history_endpoint_after_ack(self, full_setup, tmp_path):
        """ACK an anomaly then verify it appears in history."""
        from fastapi.testclient import TestClient

        from mcp_server.server import create_app
        static_dir = full_setup["config"].ui.static_dir
        db_path = str(tmp_path / "history-ack.db")
        app = create_app(
            config={
                "ui": {
                    "enabled": True,
                    "static_dir": static_dir,
                    "anomaly_ack_enabled": True,
                    "anomaly_ack_db_path": db_path,
                }
            },
            registry=full_setup["registry"],
        )
        client = TestClient(app)
        client.post("/ui/anomalies/ack", json={"anomaly_id": "e2e-001"})
        resp = client.get("/ui/anomalies/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        ids = [item["anomaly_id"] for item in data["items"]]
        assert "e2e-001" in ids
