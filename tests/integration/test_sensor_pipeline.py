"""Integration tests for sensor pipeline: config -> factory -> manager -> read."""

import pytest
from unittest.mock import Mock

from sensors.manager import SensorManager


@pytest.mark.integration
class TestSensorPipeline:
    def test_factory_to_manager_flow(self, mock_i2c_adapter, bme680_config):
        """Config -> Factory.create -> Manager.register -> initialize -> read."""
        manager = SensorManager()
        manager.create_from_config(
            "bme680", "pipeline_bme680", mock_i2c_adapter, bme680_config
        )
        assert manager.sensor_count == 1

        results = manager.initialize_all()
        assert results["pipeline_bme680"] is True

        readings = manager.read_all()
        assert "pipeline_bme680" in readings
        assert readings["pipeline_bme680"] is not None
        assert readings["pipeline_bme680"].sensor_id == "pipeline_bme680"

    def test_multi_sensor_pipeline(self, mock_i2c_adapter, mock_spi_adapter):
        """Multiple sensor types in one pipeline."""
        manager = SensorManager()
        manager.create_from_config(
            "bme680", "env_sensor", mock_i2c_adapter, {"address": 0x76}
        )
        manager.create_from_config(
            "ads1263", "adc_sensor", mock_spi_adapter,
            {"bus": 0, "device": 0, "channels": {"ch1": {"positive_input": 0, "negative_input": 1}}},
        )
        assert manager.sensor_count == 2

        results = manager.initialize_all()
        assert all(results.values())

        readings = manager.read_all()
        assert len(readings) == 2

    def test_partial_init_failure(self, mock_i2c_adapter, mock_spi_adapter):
        """One sensor fails init, others still work."""
        manager = SensorManager()
        manager.create_from_config(
            "bme680", "good_sensor", mock_i2c_adapter, {"address": 0x76}
        )

        bad_adapter = Mock()
        bad_adapter.open = Mock(side_effect=OSError("SPI fail"))
        bad_adapter.xfer2 = Mock(side_effect=OSError("SPI fail"))
        manager.create_from_config(
            "ads1263", "bad_sensor", bad_adapter, {"bus": 0, "device": 0, "channels": {}},
        )

        results = manager.initialize_all()
        assert results["good_sensor"] is True
        assert results["bad_sensor"] is False

    def test_diagnostics_pipeline(self, mock_i2c_adapter, bme680_config):
        """Full diagnostic flow."""
        manager = SensorManager()
        manager.create_from_config("bme680", "diag_sensor", mock_i2c_adapter, bme680_config)
        manager.initialize_all()

        # Read multiple times
        for _ in range(3):
            manager.read_all()

        diags = manager.get_all_diagnostics()
        assert "diag_sensor" in diags
        assert diags["diag_sensor"]["total_reads"] == 3

    def test_list_sensors(self, mock_i2c_adapter, bme680_config):
        manager = SensorManager()
        manager.create_from_config("bme680", "list_test", mock_i2c_adapter, bme680_config)
        sensors = manager.list_sensors()
        assert len(sensors) == 1
        assert sensors[0]["sensor_id"] == "list_test"
        assert sensors[0]["type"] == "BME680Sensor"

    def test_get_sensor(self, mock_i2c_adapter, bme680_config):
        manager = SensorManager()
        manager.create_from_config("bme680", "get_test", mock_i2c_adapter, bme680_config)
        assert manager.get_sensor("get_test") is not None
        assert manager.get_sensor("nope") is None

    def test_uninitialized_sensor_not_read(self, mock_i2c_adapter, bme680_config):
        """Sensors that aren't initialized should not be read."""
        manager = SensorManager()
        manager.create_from_config("bme680", "uninit", mock_i2c_adapter, bme680_config)
        # Don't call initialize_all
        readings = manager.read_all()
        assert readings["uninit"] is None
