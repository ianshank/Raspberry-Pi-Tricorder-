"""Unit tests for configuration management."""

import pytest

from utils.config import (
    TricorderConfig, I2CDeviceConfig, SPIDeviceConfig, UARTDeviceConfig,
    ADCChannelConfig, SensorConfig, ModelConfig, MCPServerConfig,
    LangGraphAgentConfig, LoggingConfig,
    load_config, _apply_env_overrides,
)


class TestI2CDeviceConfig:
    def test_valid_config(self):
        config = I2CDeviceConfig(address=0x76, bus=1)
        assert config.address == 0x76
        assert config.bus == 1
        assert config.enabled is True

    def test_address_range_low(self):
        with pytest.raises(ValueError):
            I2CDeviceConfig(address=0x01)

    def test_address_range_high(self):
        with pytest.raises(ValueError):
            I2CDeviceConfig(address=0x78)

    def test_custom_poll_rate(self):
        config = I2CDeviceConfig(address=0x33, poll_rate_hz=10.0)
        assert config.poll_rate_hz == 10.0

    def test_disabled(self):
        config = I2CDeviceConfig(address=0x33, enabled=False)
        assert config.enabled is False


class TestSPIDeviceConfig:
    def test_default_values(self):
        config = SPIDeviceConfig()
        assert config.bus == 0
        assert config.device == 0
        assert config.mode == 1
        assert config.max_speed_hz == 1000000

    def test_custom_speed(self):
        config = SPIDeviceConfig(max_speed_hz=5000000)
        assert config.max_speed_hz == 5000000


class TestUARTDeviceConfig:
    def test_default_values(self):
        config = UARTDeviceConfig()
        assert config.port == "/dev/ttyAMA0"
        assert config.baud_rate == 115200

    def test_custom_port(self):
        config = UARTDeviceConfig(port="/dev/ttyUSB0")
        assert config.port == "/dev/ttyUSB0"


class TestADCChannelConfig:
    def test_valid_channel(self):
        config = ADCChannelConfig(positive_input=0, negative_input=1, label="Test")
        assert config.positive_input == 0
        assert config.label == "Test"

    def test_invalid_input(self):
        with pytest.raises(ValueError):
            ADCChannelConfig(positive_input=10, negative_input=1, label="Bad")


class TestModelConfig:
    def test_valid_model(self):
        config = ModelConfig(
            model_path="model.onnx",
            input_shape=[1, 256, 10],
            output_shape=[1, 10],
        )
        assert config.quantization == "int8"

    def test_invalid_quantization(self):
        with pytest.raises(ValueError):
            ModelConfig(
                model_path="model.onnx",
                input_shape=[1, 256, 10],
                output_shape=[1, 10],
                quantization="invalid",
            )


class TestMCPServerConfig:
    def test_defaults(self):
        config = MCPServerConfig()
        assert config.host == "127.0.0.1"
        assert config.port == 8000

    def test_invalid_transport(self):
        with pytest.raises(ValueError):
            MCPServerConfig(transport="grpc")


class TestLangGraphAgentConfig:
    def test_defaults(self):
        config = LangGraphAgentConfig()
        assert config.model_name == "qwen2.5:3b"
        assert config.mission_mode == "patrol"

    def test_invalid_mission_mode(self):
        with pytest.raises(ValueError):
            LangGraphAgentConfig(mission_mode="attack")

    def test_invalid_threshold(self):
        with pytest.raises(ValueError):
            LangGraphAgentConfig(human_in_loop_threshold="SUPER")

    def test_severity_thresholds_default(self):
        config = LangGraphAgentConfig()
        assert config.severity_thresholds == {"critical": 0.9, "high": 0.75, "medium": 0.5}

    def test_severity_thresholds_override(self):
        config = LangGraphAgentConfig(severity_thresholds={"critical": 0.95, "high": 0.8, "medium": 0.6})
        assert config.severity_thresholds["critical"] == 0.95

    def test_severity_thresholds_partial_override_merges_defaults(self):
        config = LangGraphAgentConfig(severity_thresholds={"critical": 0.95})
        assert config.severity_thresholds == {
            "critical": 0.95,
            "high": 0.75,
            "medium": 0.5,
        }

    def test_severity_thresholds_invalid_order_rejected(self):
        with pytest.raises(ValueError, match="critical >= high >= medium"):
            LangGraphAgentConfig(
                severity_thresholds={"critical": 0.7, "high": 0.8, "medium": 0.6}
            )

    def test_severity_thresholds_invalid_type_rejected(self):
        with pytest.raises(ValueError, match="must be a dictionary"):
            LangGraphAgentConfig(severity_thresholds="not-a-dict")

    def test_max_tools_per_iteration_default(self):
        config = LangGraphAgentConfig()
        assert config.max_tools_per_iteration == 3

    def test_max_iterations_default(self):
        config = LangGraphAgentConfig()
        assert config.max_iterations == 5


class TestLoggingConfig:
    def test_defaults(self):
        config = LoggingConfig()
        assert config.level == "INFO"
        assert config.max_bytes == 10485760

    def test_invalid_level(self):
        with pytest.raises(ValueError):
            LoggingConfig(level="VERBOSE")


class TestTricorderConfig:
    def test_defaults(self):
        config = TricorderConfig()
        assert config.project_name == "Tricorder Neural Platform"
        assert config.version == "1.0.0"
        assert config.environment == "development"

    def test_invalid_environment(self):
        with pytest.raises(ValueError):
            TricorderConfig(environment="test")

    def test_extra_keys_forbidden(self):
        with pytest.raises(ValueError):
            TricorderConfig(unknown_key="value")

    def test_full_config(self):
        config = TricorderConfig(
            project_name="Test",
            sensors=SensorConfig(
                i2c_devices={"bme680": I2CDeviceConfig(address=0x76)}
            ),
        )
        assert "bme680" in config.sensors.i2c_devices


class TestLoadConfig:
    def test_load_from_file(self, test_config_path):
        config = load_config(test_config_path)
        assert config.project_name == "Test Tricorder"
        assert config.version == "1.0.0-test"

    def test_load_missing_file(self, tmp_path):
        missing = tmp_path / "nonexistent.yaml"
        config = load_config(missing)
        assert config.project_name == "Tricorder Neural Platform"  # default

    def test_load_empty_file(self, tmp_path):
        empty = tmp_path / "empty.yaml"
        empty.write_text("")
        config = load_config(empty)
        assert config.project_name == "Tricorder Neural Platform"


class TestEnvOverrides:
    def test_simple_override(self, monkeypatch):
        config_dict = {"logging": {"level": "INFO"}}
        monkeypatch.setenv("TRICORDER__LOGGING__LEVEL", "DEBUG")
        result = _apply_env_overrides(config_dict, prefix="TRICORDER")
        assert result["logging"]["level"] == "DEBUG"

    def test_nested_override(self, monkeypatch):
        """Double-underscore separator preserves underscored field names."""
        config_dict = {"mcp_server": {}}
        monkeypatch.setenv("TRICORDER__MCP_SERVER__HOST", "0.0.0.0")
        result = _apply_env_overrides(config_dict, prefix="TRICORDER")
        assert result["mcp_server"]["host"] == "0.0.0.0"

    def test_json_value_override(self, monkeypatch):
        config_dict = {"mcp_server": {}}
        monkeypatch.setenv("TRICORDER__MCP_SERVER__PORT", "9000")
        result = _apply_env_overrides(config_dict, prefix="TRICORDER")
        assert result["mcp_server"]["port"] == 9000

    def test_string_value_override(self, monkeypatch):
        config_dict = {"agent": {}}
        monkeypatch.setenv("TRICORDER__AGENT__MODEL", "llama3:8b")
        result = _apply_env_overrides(config_dict, prefix="TRICORDER")
        assert result["agent"]["model"] == "llama3:8b"

    def test_no_matching_env(self):
        config_dict = {"logging": {"level": "INFO"}}
        result = _apply_env_overrides(config_dict, prefix="TRICORDER")
        assert result["logging"]["level"] == "INFO"
