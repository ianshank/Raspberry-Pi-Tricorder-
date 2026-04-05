"""Regression tests for config migration and forward/backward compatibility."""

import pytest
from utils.config import TricorderConfig, load_config, SensorConfig, I2CDeviceConfig


@pytest.mark.regression
class TestConfigMigration:
    def test_missing_new_fields_use_defaults(self, tmp_path):
        """Config missing newer fields should still load with defaults."""
        old_config = tmp_path / "old.yaml"
        old_config.write_text("""
project_name: "Old Config"
version: "0.9.0"
environment: "development"
sensors:
  i2c_devices:
    bme680:
      address: 118
      bus: 1
      enabled: true
      poll_rate_hz: 1.0
      timeout_ms: 1000
logging:
  level: "INFO"
""")
        config = load_config(old_config)
        assert config.project_name == "Old Config"
        # New fields should have defaults
        assert config.mcp_server.port == 8000
        assert config.agent.model_name == "qwen2.5:3b"
        assert config.mqtt.host == "localhost"
        assert config.rag.top_k == 5

    def test_extra_keys_rejected(self):
        """Unknown top-level keys should be rejected."""
        with pytest.raises(ValueError):
            TricorderConfig(obsolete_field="value")

    def test_old_sensor_config_still_works(self):
        """Sensor config with only required fields works."""
        config = SensorConfig(
            i2c_devices={"bme680": I2CDeviceConfig(address=0x76)}
        )
        assert config.i2c_devices["bme680"].bus == 1  # default
        assert config.i2c_devices["bme680"].enabled is True  # default

    def test_empty_yaml_uses_all_defaults(self, tmp_path):
        """Empty YAML file should produce valid config with all defaults."""
        empty_file = tmp_path / "empty.yaml"
        empty_file.write_text("")
        config = load_config(empty_file)
        assert config.version == "1.0.0"
        assert len(config.sensors.i2c_devices) == 0  # No devices in empty config

    def test_partial_sensor_config(self, tmp_path):
        """Config with some sensors but not all should work."""
        partial = tmp_path / "partial.yaml"
        partial.write_text("""
sensors:
  i2c_devices:
    bme680:
      address: 118
      bus: 1
""")
        config = load_config(partial)
        assert "bme680" in config.sensors.i2c_devices
        assert len(config.sensors.spi_devices) == 0
        assert len(config.sensors.uart_devices) == 0
