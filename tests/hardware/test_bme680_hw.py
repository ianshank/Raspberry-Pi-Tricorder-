"""Hardware integration tests for the BME680 environmental sensor."""

from __future__ import annotations

import pytest

from sensors.bme680 import BME680Sensor


@pytest.mark.hardware
@pytest.mark.sensor_required("bme680")
class TestBME680Hardware:
    def test_initialize(self, real_i2c_adapter, bme680_config):
        sensor = BME680Sensor("bme680", real_i2c_adapter, bme680_config)
        assert sensor.initialize() is True

    def test_read_returns_valid_data(self, real_i2c_adapter, bme680_config):
        sensor = BME680Sensor("bme680", real_i2c_adapter, bme680_config)
        sensor.initialize()
        reading = sensor.read()
        assert reading.value is not None
        assert "temperature_c" in reading.value
