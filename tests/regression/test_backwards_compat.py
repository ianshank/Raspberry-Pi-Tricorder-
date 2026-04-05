"""Regression tests ensuring backwards compatibility."""

import pytest
from unittest.mock import Mock
from datetime import datetime, timezone

from sensors.base import (
    SensorReading, SensorStatus, BaseSensor, SensorFactory,
    SensorError, SensorInitializationError, SensorCommunicationError,
    I2CAdapter, SPIAdapter, UARTAdapter,
)
from utils.config import (
    TricorderConfig, I2CDeviceConfig, SPIDeviceConfig, UARTDeviceConfig,
    SensorConfig, MCPServerConfig, LoggingConfig,
)
from models.base import ModelResult, ModelStatus, ModelRegistry
from mcp_server.server import ToolRegistry, Tool


@pytest.mark.regression
class TestSensorAPICompat:
    """Ensure sensor base API remains stable."""

    def test_sensor_reading_fields(self):
        """SensorReading must always have these fields."""
        reading = SensorReading(
            sensor_id="test",
            timestamp=datetime.now(timezone.utc),
            value=42,
        )
        assert hasattr(reading, 'sensor_id')
        assert hasattr(reading, 'timestamp')
        assert hasattr(reading, 'value')
        assert hasattr(reading, 'unit')
        assert hasattr(reading, 'confidence')
        assert hasattr(reading, 'metadata')

    def test_sensor_reading_to_dict_keys(self):
        """to_dict() output must always contain these keys."""
        reading = SensorReading(
            sensor_id="test",
            timestamp=datetime.now(timezone.utc),
            value=42,
        )
        d = reading.to_dict()
        required_keys = {"sensor_id", "timestamp", "value", "unit", "confidence", "metadata"}
        assert required_keys == set(d.keys())

    def test_base_sensor_interface(self):
        """BaseSensor must always provide these methods."""
        required_methods = [
            "initialize", "read", "calibrate", "reset",
            "get_status", "get_last_reading", "get_diagnostics",
        ]
        for method in required_methods:
            assert hasattr(BaseSensor, method)

    def test_sensor_factory_interface(self):
        """SensorFactory must always provide create/register."""
        assert hasattr(SensorFactory, 'create')
        assert hasattr(SensorFactory, 'register')
        assert hasattr(SensorFactory, 'list_types')

    def test_sensor_status_values(self):
        """SensorStatus must always have these members."""
        expected = {"UNINITIALIZED", "READY", "READING", "ERROR", "CALIBRATING", "DISABLED"}
        actual = {s.name for s in SensorStatus}
        assert expected == actual

    def test_exception_hierarchy(self):
        """Exception hierarchy must be stable."""
        assert issubclass(SensorInitializationError, SensorError)
        assert issubclass(SensorCommunicationError, SensorError)


@pytest.mark.regression
class TestConfigCompat:
    """Ensure config schema backwards compatibility."""

    def test_default_config_creates(self):
        """Default TricorderConfig must always work with no args."""
        config = TricorderConfig()
        assert config.project_name == "Tricorder Neural Platform"

    def test_i2c_config_has_required_fields(self):
        """I2CDeviceConfig must always support these fields."""
        config = I2CDeviceConfig(address=0x76)
        assert hasattr(config, 'address')
        assert hasattr(config, 'bus')
        assert hasattr(config, 'enabled')
        assert hasattr(config, 'poll_rate_hz')
        assert hasattr(config, 'timeout_ms')

    def test_mcp_config_has_required_fields(self):
        config = MCPServerConfig()
        assert hasattr(config, 'host')
        assert hasattr(config, 'port')
        assert hasattr(config, 'transport')
        assert hasattr(config, 'auth_enabled')

    def test_config_with_minimal_yaml(self, tmp_path):
        """Minimal YAML (just project_name) should load with defaults."""
        from utils.config import load_config
        cfg_file = tmp_path / "minimal.yaml"
        cfg_file.write_text("project_name: Minimal\n")
        config = load_config(cfg_file)
        assert config.project_name == "Minimal"
        assert config.logging.level == "INFO"  # default


@pytest.mark.regression
class TestMCPToolCompat:
    """Ensure MCP tool interfaces remain stable."""

    def test_tool_model_fields(self):
        tool = Tool(name="test", description="desc", inputSchema={"type": "object"})
        assert hasattr(tool, 'name')
        assert hasattr(tool, 'description')
        assert hasattr(tool, 'inputSchema')

    def test_registry_interface(self):
        registry = ToolRegistry()
        assert hasattr(registry, 'register')
        assert hasattr(registry, 'register_function')
        assert hasattr(registry, 'call')
        assert hasattr(registry, 'list_tools')
        assert hasattr(registry, 'has_tool')


@pytest.mark.regression
class TestModelCompat:
    """Ensure model API stability."""

    def test_model_result_fields(self):
        result = ModelResult(output=42)
        d = result.to_dict()
        assert "output" in d
        assert "confidence" in d
        assert "inference_time_ms" in d
        assert "metadata" in d

    def test_model_status_values(self):
        expected = {"UNLOADED", "LOADED", "RUNNING", "ERROR"}
        actual = {s.name for s in ModelStatus}
        assert expected == actual

    def test_model_registry_interface(self):
        assert hasattr(ModelRegistry, 'register_type')
        assert hasattr(ModelRegistry, 'create')
        assert hasattr(ModelRegistry, 'get')
        assert hasattr(ModelRegistry, 'list_types')
