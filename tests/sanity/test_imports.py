"""Sanity tests for module imports — catches circular dependencies."""

import pytest


@pytest.mark.sanity
class TestImports:
    def test_import_config(self):
        from utils.config import TricorderConfig
        assert TricorderConfig is not None

    def test_import_logging_setup(self):
        from utils.logging_setup import setup_logging
        assert setup_logging is not None

    def test_import_sensor_base(self):
        from sensors.base import (
            BaseSensor,
        )
        assert BaseSensor is not None

    def test_import_sensor_drivers(self):
        from sensors.bme680 import BME680Sensor
        assert BME680Sensor is not None

    def test_import_sensor_manager(self):
        from sensors.manager import SensorManager
        assert SensorManager is not None

    def test_import_model_base(self):
        from models.base import (
            BaseModel,
        )
        assert BaseModel is not None

    def test_import_anomaly_detector(self):
        from models.anomaly_detector import AnomalyDetector
        assert AnomalyDetector is not None

    def test_import_fusion_engine(self):
        from models.fusion_engine import FusionEngine
        assert FusionEngine is not None

    def test_import_mcp_server(self):
        from mcp_server.server import create_app
        assert create_app is not None

    def test_import_sensor_tools(self):
        from mcp_server.tools.sensor_tools import register_sensor_tools
        assert register_sensor_tools is not None

    def test_import_anomaly_tools(self):
        from mcp_server.tools.anomaly_tools import register_anomaly_tools
        assert register_anomaly_tools is not None

    def test_import_agent(self):
        from agents.langgraph_agent import TricorderAgent
        assert TricorderAgent is not None

    def test_no_circular_imports(self):
        """Import all modules to check for circular dependencies."""
        import importlib
        modules = [
            "utils.config",
            "utils.logging_setup",
            "sensors.base",
            "sensors.bme680",
            "sensors.mlx90640",
            "sensors.as7265x",
            "sensors.max30102",
            "sensors.ads1263",
            "sensors.hlk_ld2410",
            "sensors.tfmini_s",
            "sensors.manager",
            "models.base",
            "models.anomaly_detector",
            "models.fusion_engine",
            "mcp_server.server",
            "mcp_server.tools.sensor_tools",
            "mcp_server.tools.anomaly_tools",
            "agents.langgraph_agent",
        ]
        for mod in modules:
            importlib.import_module(mod)
