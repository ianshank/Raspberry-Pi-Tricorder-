"""Unit tests for all concrete sensor drivers."""

from unittest.mock import Mock

import pytest

from sensors.ads1263 import ADS1263Sensor
from sensors.as7265x import AS7265xSensor
from sensors.base import (
    SensorCommunicationError,
    SensorFactory,
    SensorInitializationError,
    SensorStatus,
)
from sensors.bme680 import BME680Sensor
from sensors.hlk_ld2410 import HLKLD2410Sensor
from sensors.max30102 import MAX30102Sensor
from sensors.mlx90640 import MLX90640Sensor
from sensors.tfmini_s import TFMiniSSensor

# ========== BME680 ==========

class TestBME680Sensor:
    def test_init_success(self, mock_i2c_adapter, bme680_config):
        sensor = BME680Sensor("bme680_01", mock_i2c_adapter, bme680_config)
        assert sensor.initialize() is True
        assert sensor.status == SensorStatus.READY
        mock_i2c_adapter.read_byte_data.assert_called_once_with(0x76, 0xD0)

    def test_init_wrong_chip_id(self, mock_i2c_adapter, bme680_config):
        mock_i2c_adapter.read_byte_data.return_value = 0xFF
        sensor = BME680Sensor("bme680_01", mock_i2c_adapter, bme680_config)
        with pytest.raises(SensorInitializationError, match="chip ID mismatch"):
            sensor.initialize()

    def test_init_i2c_error(self, mock_i2c_adapter, bme680_config):
        mock_i2c_adapter.read_byte_data.side_effect = OSError("bus error")
        sensor = BME680Sensor("bme680_01", mock_i2c_adapter, bme680_config)
        with pytest.raises(SensorInitializationError):
            sensor.initialize()
        assert sensor.status == SensorStatus.ERROR

    def test_read_success(self, mock_i2c_adapter, bme680_config):
        sensor = BME680Sensor("bme680_01", mock_i2c_adapter, bme680_config)
        sensor.initialize()
        reading = sensor.read()
        assert reading.sensor_id == "bme680_01"
        assert "temperature_c" in reading.value
        assert "humidity_rh" in reading.value
        assert "pressure_hpa" in reading.value
        assert "gas_resistance_ohm" in reading.value
        assert reading.confidence > 0

    def test_read_error(self, mock_i2c_adapter, bme680_config):
        sensor = BME680Sensor("bme680_01", mock_i2c_adapter, bme680_config)
        sensor.initialize()
        mock_i2c_adapter.read_i2c_block_data.side_effect = OSError("read error")
        with pytest.raises(SensorCommunicationError):
            sensor.read()

    def test_diagnostics_after_reads(self, mock_i2c_adapter, bme680_config):
        sensor = BME680Sensor("bme680_01", mock_i2c_adapter, bme680_config)
        sensor.initialize()
        for _ in range(5):
            sensor.read()
        diag = sensor.get_diagnostics()
        assert diag["total_reads"] == 5
        assert diag["error_count"] == 0

    def test_calibrate(self, mock_i2c_adapter, bme680_config):
        sensor = BME680Sensor("bme680_01", mock_i2c_adapter, bme680_config)
        sensor.initialize()
        assert sensor.calibrate() is True

    def test_config_address(self, mock_i2c_adapter):
        config = {"address": 0x77}
        sensor = BME680Sensor("bme680_alt", mock_i2c_adapter, config)
        assert sensor.address == 0x77


# ========== MLX90640 ==========

class TestMLX90640Sensor:
    def test_init_success(self, mock_i2c_mlx90640, mlx90640_config):
        sensor = MLX90640Sensor("mlx_01", mock_i2c_mlx90640, mlx90640_config)
        assert sensor.initialize() is True
        assert sensor.status == SensorStatus.READY

    def test_init_error(self, mock_i2c_mlx90640, mlx90640_config):
        mock_i2c_mlx90640.read_i2c_block_data.side_effect = OSError("fail")
        sensor = MLX90640Sensor("mlx_01", mock_i2c_mlx90640, mlx90640_config)
        with pytest.raises(SensorInitializationError):
            sensor.initialize()

    def test_read_success(self, mock_i2c_mlx90640, mlx90640_config):
        sensor = MLX90640Sensor("mlx_01", mock_i2c_mlx90640, mlx90640_config)
        sensor.initialize()
        reading = sensor.read()
        assert "thermal_frame" in reading.value
        assert reading.value["rows"] == 24
        assert reading.value["cols"] == 32
        assert len(reading.value["thermal_frame"]) == 24 * 32

    def test_read_error(self, mock_i2c_mlx90640, mlx90640_config):
        sensor = MLX90640Sensor("mlx_01", mock_i2c_mlx90640, mlx90640_config)
        sensor.initialize()
        mock_i2c_mlx90640.read_i2c_block_data.side_effect = OSError("read fail")
        with pytest.raises(SensorCommunicationError):
            sensor.read()


# ========== AS7265x ==========

class TestAS7265xSensor:
    def test_init_success(self, mock_i2c_as7265x, as7265x_config):
        sensor = AS7265xSensor("spectral_01", mock_i2c_as7265x, as7265x_config)
        assert sensor.initialize() is True

    def test_init_hw_version_mismatch(self, mock_i2c_as7265x, as7265x_config):
        mock_i2c_as7265x.read_byte_data = Mock(return_value=0x00)
        sensor = AS7265xSensor("spectral_01", mock_i2c_as7265x, as7265x_config)
        with pytest.raises(SensorInitializationError, match="HW version"):
            sensor.initialize()

    def test_read_success(self, mock_i2c_as7265x, as7265x_config):
        sensor = AS7265xSensor("spectral_01", mock_i2c_as7265x, as7265x_config)
        sensor.initialize()
        reading = sensor.read()
        assert "spectral_channels" in reading.value
        assert reading.value["channel_count"] == 18

    def test_read_error(self, mock_i2c_as7265x, as7265x_config):
        sensor = AS7265xSensor("spectral_01", mock_i2c_as7265x, as7265x_config)
        sensor.initialize()
        mock_i2c_as7265x.read_i2c_block_data.side_effect = OSError("fail")
        with pytest.raises(SensorCommunicationError):
            sensor.read()


# ========== MAX30102 ==========

class TestMAX30102Sensor:
    def test_init_success(self, mock_i2c_max30102, max30102_config):
        sensor = MAX30102Sensor("hr_01", mock_i2c_max30102, max30102_config)
        assert sensor.initialize() is True

    def test_init_wrong_part_id(self, mock_i2c_max30102, max30102_config):
        mock_i2c_max30102.read_byte_data = Mock(return_value=0xFF)
        sensor = MAX30102Sensor("hr_01", mock_i2c_max30102, max30102_config)
        with pytest.raises(SensorInitializationError, match="part ID"):
            sensor.initialize()

    def test_read_success(self, mock_i2c_max30102, max30102_config):
        sensor = MAX30102Sensor("hr_01", mock_i2c_max30102, max30102_config)
        sensor.initialize()
        reading = sensor.read()
        assert "spo2_percent" in reading.value
        assert "heart_rate_bpm" in reading.value

    def test_read_error(self, mock_i2c_max30102, max30102_config):
        sensor = MAX30102Sensor("hr_01", mock_i2c_max30102, max30102_config)
        sensor.initialize()
        mock_i2c_max30102.read_byte_data.side_effect = OSError("fail")
        with pytest.raises(SensorCommunicationError):
            sensor.read()

    def test_partial_hr_bounds_override_merges_defaults(self, mock_i2c_max30102, max30102_config):
        config = dict(max30102_config)
        config["hr_bounds"] = {"max_bpm": 180}
        sensor = MAX30102Sensor("hr_01", mock_i2c_max30102, config)
        assert sensor.hr_bounds["min_bpm"] == 40.0
        assert sensor.hr_bounds["max_bpm"] == 180.0

    def test_invalid_hr_bounds_rejected(self, mock_i2c_max30102, max30102_config):
        config = dict(max30102_config)
        config["hr_bounds"] = {"min_bpm": 200, "max_bpm": 100}
        with pytest.raises(ValueError, match="min_bpm < max_bpm"):
            MAX30102Sensor("hr_01", mock_i2c_max30102, config)


# ========== ADS1263 ==========

class TestADS1263Sensor:
    def test_init_success(self, mock_spi_adapter, ads1263_config):
        sensor = ADS1263Sensor("adc_01", mock_spi_adapter, ads1263_config)
        assert sensor.initialize() is True
        mock_spi_adapter.open.assert_called_once_with(0, 0)

    def test_init_id_mismatch(self, mock_spi_adapter, ads1263_config):
        mock_spi_adapter.xfer2 = Mock(return_value=[0x00, 0x00, 0xFF, 0x00, 0x00, 0x00])
        sensor = ADS1263Sensor("adc_01", mock_spi_adapter, ads1263_config)
        with pytest.raises(SensorInitializationError, match="ID mismatch"):
            sensor.initialize()

    def test_read_success(self, mock_spi_adapter, ads1263_config):
        sensor = ADS1263Sensor("adc_01", mock_spi_adapter, ads1263_config)
        sensor.initialize()
        reading = sensor.read()
        assert "channels" in reading.value
        assert reading.value["channel_count"] == 2

    def test_read_channel(self, mock_spi_adapter, ads1263_config):
        sensor = ADS1263Sensor("adc_01", mock_spi_adapter, ads1263_config)
        sensor.initialize()
        voltage = sensor.read_channel(0, 1)
        assert isinstance(voltage, float)

    def test_reset(self, mock_spi_adapter, ads1263_config):
        sensor = ADS1263Sensor("adc_01", mock_spi_adapter, ads1263_config)
        sensor.initialize()
        assert sensor.reset() is True
        assert sensor.status == SensorStatus.UNINITIALIZED


# ========== HLK-LD2410 ==========

class TestHLKLD2410Sensor:
    def test_init_success(self, mock_uart_adapter, hlk_ld2410_config):
        sensor = HLKLD2410Sensor("radar_01", mock_uart_adapter, hlk_ld2410_config)
        assert sensor.initialize() is True

    def test_init_no_response(self, mock_uart_adapter, hlk_ld2410_config):
        mock_uart_adapter.read = Mock(return_value=None)
        sensor = HLKLD2410Sensor("radar_01", mock_uart_adapter, hlk_ld2410_config)
        with pytest.raises(SensorInitializationError):
            sensor.initialize()

    def test_read_success(self, mock_uart_adapter, hlk_ld2410_config):
        sensor = HLKLD2410Sensor("radar_01", mock_uart_adapter, hlk_ld2410_config)
        sensor.initialize()
        reading = sensor.read()
        assert "target_state" in reading.value
        assert "moving_target_distance_cm" in reading.value

    def test_read_no_data(self, mock_uart_adapter, hlk_ld2410_config):
        sensor = HLKLD2410Sensor("radar_01", mock_uart_adapter, hlk_ld2410_config)
        sensor.initialize()
        mock_uart_adapter.read = Mock(return_value=b'')
        with pytest.raises(SensorCommunicationError):
            sensor.read()

    def test_parse_invalid_frame(self, mock_uart_adapter, hlk_ld2410_config):
        sensor = HLKLD2410Sensor("radar_01", mock_uart_adapter, hlk_ld2410_config)
        sensor.initialize()
        mock_uart_adapter.read = Mock(return_value=b'\x00\x01\x02')
        with pytest.raises(SensorCommunicationError):
            sensor.read()


# ========== TFmini-S ==========

class TestTFMiniSSensor:
    def test_init_success(self, mock_uart_tfmini, tfmini_config):
        sensor = TFMiniSSensor("lidar_01", mock_uart_tfmini, tfmini_config)
        assert sensor.initialize() is True

    def test_read_success(self, mock_uart_tfmini, tfmini_config):
        sensor = TFMiniSSensor("lidar_01", mock_uart_tfmini, tfmini_config)
        sensor.initialize()
        reading = sensor.read()
        assert "distance_cm" in reading.value
        assert "signal_strength" in reading.value
        assert reading.value["distance_cm"] == 150

    def test_read_no_data(self, mock_uart_tfmini, tfmini_config):
        sensor = TFMiniSSensor("lidar_01", mock_uart_tfmini, tfmini_config)
        sensor.initialize()
        mock_uart_tfmini.read = Mock(return_value=b'')
        with pytest.raises(SensorCommunicationError):
            sensor.read()

    def test_read_invalid_frame(self, mock_uart_tfmini, tfmini_config):
        sensor = TFMiniSSensor("lidar_01", mock_uart_tfmini, tfmini_config)
        sensor.initialize()
        mock_uart_tfmini.read = Mock(return_value=b'\x00' * 27)  # No valid header
        with pytest.raises(SensorCommunicationError):
            sensor.read()

    def test_out_of_range(self, mock_uart_tfmini, tfmini_config):
        """Test that out-of-range readings get low confidence."""
        dist = 2000  # Over max_range_cm
        strength = 100
        temp_raw = 2048
        frame_bytes = [
            0x59, 0x59,
            dist & 0xFF, (dist >> 8) & 0xFF,
            strength & 0xFF, (strength >> 8) & 0xFF,
            temp_raw & 0xFF, (temp_raw >> 8) & 0xFF,
        ]
        checksum = sum(frame_bytes) & 0xFF
        frame_bytes.append(checksum)
        mock_uart_tfmini.read = Mock(return_value=bytes(frame_bytes * 3))

        sensor = TFMiniSSensor("lidar_01", mock_uart_tfmini, tfmini_config)
        sensor.initialize()
        reading = sensor.read()
        assert reading.confidence < 0.5  # Out of range = low confidence


# ========== FACTORY REGISTRATION ==========

class TestFactoryRegistration:
    def test_all_drivers_registered(self):
        expected = ["bme680", "mlx90640", "as7265x", "max30102", "ads1263", "hlk_ld2410", "tfmini_s"]
        registered = SensorFactory.list_types()
        for sensor_type in expected:
            assert sensor_type in registered, f"{sensor_type} not registered"
