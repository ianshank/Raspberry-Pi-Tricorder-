"""Tests covering previously-uncovered sensor driver paths.

Covers:
- ADS1263: short SPI response (voltage=0), read exception, reset success/failure
- MAX30102: _normalize_hr_bounds validation branches, empty FIFO → num_samples=1
- MLX90640: negative raw pixel (signed conversion), pixel padding
- AS7265x: init generic exception path
- HLK-LD2410: _parse_data_frame short/missing-header, read exception
- TFmini-S: _parse_frame checksum mismatch, init no-response, read exception
- SensorManager: read_all exception → None
"""

import pytest
from unittest.mock import Mock

from sensors.ads1263 import ADS1263Sensor
from sensors.as7265x import AS7265xSensor
from sensors.hlk_ld2410 import HLKLD2410Sensor
from sensors.max30102 import MAX30102Sensor
from sensors.mlx90640 import MLX90640Sensor
from sensors.tfmini_s import TFMiniSSensor
from sensors.manager import SensorManager
from sensors.base import (
    SensorStatus,
    SensorCommunicationError,
    SensorInitializationError,
)


# ========== ADS1263 ==========

class TestADS1263Coverage:
    """Lines 125, 128, 158-160, 168-170."""

    def test_short_spi_response_yields_zero_voltage(self, mock_spi_adapter, ads1263_config):
        """Lines 127-128: len(response) < 5 → voltage = 0.0.

        Initialize with full responses, then swap to short response only for
        the actual data-read call (read1 command = 0x12).
        """
        # xfer2 returns full init response by default; after init we switch it
        sensor = ADS1263Sensor("ads_01", mock_spi_adapter, ads1263_config)
        sensor.initialize()
        # Now override: data-read returns only 2 bytes
        mock_spi_adapter.xfer2.return_value = [0x00, 0x01]
        voltage = sensor.read_channel(0, 1)
        assert voltage == 0.0

    def test_negative_raw_value(self, mock_spi_adapter, ads1263_config):
        """Line 124-125: raw > 0x7FFFFFFF wraps to negative."""
        sensor = ADS1263Sensor("ads_01", mock_spi_adapter, ads1263_config)
        sensor.initialize()
        # Build 6-byte read response where bytes 1-4 encode 0x80000000
        raw_val = 0x80000000
        b = [(raw_val >> (8 * i)) & 0xFF for i in range(3, -1, -1)]
        mock_spi_adapter.xfer2.return_value = [0x00] + b + [0x00]
        voltage = sensor.read_channel(0, 1)
        assert voltage < 0.0

    def test_read_exception_raises_communication_error(self, mock_spi_adapter, ads1263_config):
        """Lines 158-160: exception during read → SensorCommunicationError."""
        sensor = ADS1263Sensor("ads_01", mock_spi_adapter, ads1263_config)
        sensor.initialize()
        mock_spi_adapter.xfer2.side_effect = RuntimeError("SPI bus error")
        with pytest.raises(SensorCommunicationError, match="ADS1263 read failed"):
            sensor.read()

    def test_reset_success(self, mock_spi_adapter, ads1263_config):
        """Lines 162-170: reset succeeds → UNINITIALIZED status."""
        mock_spi_adapter.xfer2.return_value = [0x00, 0x00, 0x01, 0x00, 0x00]
        sensor = ADS1263Sensor("ads_01", mock_spi_adapter, ads1263_config)
        sensor.initialize()
        assert sensor.reset() is True
        assert sensor.status == SensorStatus.UNINITIALIZED

    def test_reset_failure_returns_false(self, mock_spi_adapter, ads1263_config):
        """Lines 168-170: xfer2 raises during reset → returns False."""
        sensor = ADS1263Sensor("ads_01", mock_spi_adapter, ads1263_config)
        sensor.initialize()
        mock_spi_adapter.xfer2.side_effect = RuntimeError("SPI error")
        assert sensor.reset() is False


# ========== MAX30102 ==========

class TestMAX30102Coverage:
    """Lines 54, 62, 66-67, 70, 135-137, 152."""

    def test_hr_bounds_none_uses_defaults(self):
        """Line 51-52: None input returns defaults."""
        result = MAX30102Sensor._normalize_hr_bounds(None)
        assert result == {"min_bpm": 40.0, "max_bpm": 200.0}

    def test_hr_bounds_non_dict_raises(self):
        """Line 53-54: non-dict raises ValueError."""
        with pytest.raises(ValueError, match="must be a dictionary"):
            MAX30102Sensor._normalize_hr_bounds("invalid")

    def test_hr_bounds_explicit_none_value_raises(self):
        """Line 61-62: key present but value is None triggers 'must include both'."""
        with pytest.raises(ValueError, match="must include both"):
            MAX30102Sensor._normalize_hr_bounds({"min_bpm": None, "max_bpm": 200})

    def test_hr_bounds_non_numeric_raises(self):
        """Lines 63-67: non-numeric values."""
        with pytest.raises(ValueError, match="must be numeric"):
            MAX30102Sensor._normalize_hr_bounds({"min_bpm": "fast", "max_bpm": 200})

    def test_hr_bounds_non_positive_raises(self):
        """Lines 69-70: zero/negative values."""
        with pytest.raises(ValueError, match="must be positive"):
            MAX30102Sensor._normalize_hr_bounds({"min_bpm": 0, "max_bpm": 200})

    def test_hr_bounds_min_gte_max_raises(self):
        """Lines 71-72: min >= max."""
        with pytest.raises(ValueError, match="min_bpm < max_bpm"):
            MAX30102Sensor._normalize_hr_bounds({"min_bpm": 200, "max_bpm": 100})

    def test_equal_min_max_raises(self):
        with pytest.raises(ValueError, match="min_bpm < max_bpm"):
            MAX30102Sensor._normalize_hr_bounds({"min_bpm": 100, "max_bpm": 100})

    def test_init_generic_exception_wrapped(self, mock_i2c_max30102, max30102_config):
        """Lines 135-137: non-SensorInitializationError wrapped."""
        mock_i2c_max30102.read_byte_data = Mock(side_effect=OSError("I2C bus error"))
        sensor = MAX30102Sensor("max_01", mock_i2c_max30102, max30102_config)
        with pytest.raises(SensorInitializationError, match="MAX30102 init failed"):
            sensor.initialize()

    def test_read_zero_fifo_forces_one_sample(self, mock_i2c_max30102, max30102_config):
        """Line 151-152: write_ptr == read_ptr → num_samples forced to 1."""
        # Return part ID on first call, then write_ptr=5, read_ptr=5 (0 samples)
        call_count = [0]
        def side_effect(addr, reg):
            call_count[0] += 1
            if reg == 0xFF:
                return 0x15  # part ID
            if reg == 0x04:
                return 5   # write_ptr
            if reg == 0x06:
                return 5   # read_ptr (same as write → 0 samples → forces 1)
            return 0x00
        mock_i2c_max30102.read_byte_data = Mock(side_effect=side_effect)
        mock_i2c_max30102.read_i2c_block_data = Mock(
            return_value=[0x01, 0x80, 0x40, 0x02, 0x60, 0x30]
        )
        sensor = MAX30102Sensor("max_01", mock_i2c_max30102, max30102_config)
        sensor.initialize()
        reading = sensor.read()
        assert reading is not None


# ========== MLX90640 ==========

class TestMLX90640Coverage:
    """Lines 90, 96."""

    def test_negative_raw_pixel_sign_conversion(self, mock_i2c_mlx90640, mlx90640_config):
        """Line 89-90: raw > 32767 → subtract 65536 → negative temp."""
        # Pixel data: 0xFF, 0xFF = 65535 → raw=65535 > 32767 → raw -= 65536 → raw=-1
        # temp_c = -1 * 0.02 = -0.02°C
        full_frame = [0xFF, 0xFF] * (24 * 32)  # 768 pixels × 2 bytes
        mock_i2c_mlx90640.read_i2c_block_data = Mock(return_value=full_frame)
        sensor = MLX90640Sensor("mlx_01", mock_i2c_mlx90640, mlx90640_config)
        sensor.initialize()
        reading = sensor.read()
        assert reading.value["min_temp_c"] < 0.0

    def test_short_read_padded_with_zeros(self, mock_i2c_mlx90640, mlx90640_config):
        """Line 94-96: fewer raw bytes than expected → pixels padded with 0.0.

        chunk_size=32 → 48 chunks needed for 768 pixels.
        Each call returns 2 bytes → 1 pixel per chunk → 48 pixels read.
        Remaining 768-48=720 are padded with 0.0.
        """
        mock_i2c_mlx90640.read_i2c_block_data = Mock(return_value=[0x00, 0x80])  # 1 pixel
        sensor = MLX90640Sensor("mlx_01", mock_i2c_mlx90640, mlx90640_config)
        sensor.initialize()
        reading = sensor.read()
        thermal = reading.value["thermal_frame"]
        assert len(thermal) == 24 * 32
        # Pixels at index ≥48 are padded with 0.0
        assert thermal[48] == 0.0
        assert thermal[767] == 0.0


# ========== AS7265x ==========

class TestAS7265xCoverage:
    """Lines 99-101: generic exception during init → SensorInitializationError."""

    def test_init_generic_exception_wrapped(self, mock_i2c_as7265x, as7265x_config):
        """Line 99-101: OSError during init → wraps to SensorInitializationError."""
        mock_i2c_as7265x.read_byte_data = Mock(side_effect=OSError("I2C dead"))
        sensor = AS7265xSensor("as_01", mock_i2c_as7265x, as7265x_config)
        with pytest.raises(SensorInitializationError, match="AS7265x init failed"):
            sensor.initialize()


# ========== HLK-LD2410 ==========

class TestHLKLD2410Coverage:
    """Lines 74, 78, 153-155."""

    def test_parse_data_frame_too_short(self, mock_uart_adapter, hlk_ld2410_config):
        """Line 68-69: frame < 23 bytes returns None."""
        sensor = HLKLD2410Sensor("ld_01", mock_uart_adapter, hlk_ld2410_config)
        assert sensor._parse_data_frame(b"\x01\x02") is None

    def test_parse_data_frame_no_header(self, mock_uart_adapter, hlk_ld2410_config):
        """Lines 72-74: header not found returns None."""
        sensor = HLKLD2410Sensor("ld_01", mock_uart_adapter, hlk_ld2410_config)
        bad_frame = bytes(30)  # 30 zero bytes, no header
        assert sensor._parse_data_frame(bad_frame) is None

    def test_parse_data_frame_header_too_close_to_end(self, mock_uart_adapter, hlk_ld2410_config):
        """Lines 72-74: header found but idx + 23 > len → None."""
        sensor = HLKLD2410Sensor("ld_01", mock_uart_adapter, hlk_ld2410_config)
        # Header at byte 10 of a 25-byte buffer → idx(10) + 23 = 33 > 25
        frame = bytes(10) + b'\xF4\xF3\xF2\xF1' + bytes(11)
        assert sensor._parse_data_frame(frame) is None

    def test_read_generic_exception_raises_communication_error(self, mock_uart_adapter, hlk_ld2410_config):
        """Lines 153-155: non-SensorCommunicationError wrapped."""
        sensor = HLKLD2410Sensor("ld_01", mock_uart_adapter, hlk_ld2410_config)
        sensor.initialize()
        mock_uart_adapter.read = Mock(side_effect=OSError("UART crash"))
        with pytest.raises(SensorCommunicationError, match="LD2410 read failed"):
            sensor.read()


# ========== TFMini-S ==========

class TestTFMiniSCoverage:
    """Lines 50, 60, 84, 93-95, 124-126."""

    def test_parse_frame_too_short(self, mock_uart_tfmini, tfmini_config):
        """Line 49-50: data shorter than FRAME_LENGTH → None."""
        sensor = TFMiniSSensor("tf_01", mock_uart_tfmini, tfmini_config)
        assert sensor._parse_frame(b"\x59\x59\x01") is None

    def test_parse_frame_bad_checksum(self, mock_uart_tfmini, tfmini_config):
        """Line 59-60: checksum mismatch skips frame → returns None."""
        sensor = TFMiniSSensor("tf_01", mock_uart_tfmini, tfmini_config)
        # Valid-looking header but wrong checksum byte
        frame = bytes([0x59, 0x59, 0x96, 0x00, 0x2C, 0x01, 0x40, 0x09, 0xFF])
        assert sensor._parse_frame(frame) is None

    def test_init_no_response_continues(self, mock_uart_tfmini, tfmini_config):
        """Lines 83-84: no version response → logs warning but still succeeds."""
        mock_uart_tfmini.read = Mock(return_value=b"")  # empty response
        sensor = TFMiniSSensor("tf_01", mock_uart_tfmini, tfmini_config)
        assert sensor.initialize() is True

    def test_init_exception_raises_initialization_error(self, mock_uart_tfmini, tfmini_config):
        """Lines 93-95: write() raises → SensorInitializationError."""
        mock_uart_tfmini.write = Mock(side_effect=OSError("UART error"))
        sensor = TFMiniSSensor("tf_01", mock_uart_tfmini, tfmini_config)
        with pytest.raises(SensorInitializationError, match="TFmini-S init failed"):
            sensor.initialize()

    def test_read_generic_exception_raises_communication_error(self, mock_uart_tfmini, tfmini_config):
        """Lines 124-126: non-SensorCommunicationError wrapped."""
        sensor = TFMiniSSensor("tf_01", mock_uart_tfmini, tfmini_config)
        sensor.initialize()
        mock_uart_tfmini.read = Mock(side_effect=OSError("UART dead"))
        with pytest.raises(SensorCommunicationError, match="TFmini-S read failed"):
            sensor.read()


# ========== SensorManager ==========

class TestSensorManagerCoverage:
    """Lines 56-58: read_all handles read() exception gracefully."""

    def test_read_all_exception_returns_none_for_sensor(self):
        """Lines 56-58: sensor.read() raises → reading stored as None."""
        failing_sensor = Mock()
        failing_sensor.get_status.return_value = SensorStatus.READY
        failing_sensor.read.side_effect = RuntimeError("sensor dead")

        manager = SensorManager()
        manager._sensors["bad_sensor"] = failing_sensor

        readings = manager.read_all()
        assert "bad_sensor" in readings
        assert readings["bad_sensor"] is None
