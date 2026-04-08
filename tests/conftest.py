"""Shared test fixtures for Tricorder Neural Platform."""

import sys
from pathlib import Path
from unittest.mock import Mock, PropertyMock
from datetime import datetime, timezone

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ========== I2C ADAPTER FIXTURES ==========

@pytest.fixture
def mock_i2c_adapter():
    """Mock I2C adapter that simulates BME680 by default."""
    adapter = Mock()
    adapter.read_byte_data = Mock(return_value=0x61)  # BME680 chip ID
    adapter.write_byte_data = Mock()
    adapter.read_i2c_block_data = Mock(return_value=[0x80, 0x40, 0x20, 0x10])
    adapter.write_i2c_block_data = Mock()
    adapter.write_byte = Mock()
    return adapter


@pytest.fixture
def mock_i2c_mlx90640():
    """Mock I2C adapter for MLX90640."""
    adapter = Mock()
    adapter.read_byte_data = Mock(return_value=0x00)
    adapter.write_byte_data = Mock()
    # Return enough bytes for thermal frame chunks
    adapter.read_i2c_block_data = Mock(return_value=[0x00, 0x80] * 16)
    adapter.write_i2c_block_data = Mock()
    return adapter


@pytest.fixture
def mock_i2c_as7265x():
    """Mock I2C adapter for AS7265x spectral sensor."""
    adapter = Mock()
    adapter.read_byte_data = Mock(side_effect=lambda addr, reg: {
        0x00: 0x00,  # status ready
        0x02: 0x40,  # HW version
    }.get(reg, 0x00))
    adapter.write_byte_data = Mock()
    adapter.read_i2c_block_data = Mock(return_value=[0x10, 0x20])
    return adapter


@pytest.fixture
def mock_i2c_max30102():
    """Mock I2C adapter for MAX30102."""
    adapter = Mock()
    adapter.read_byte_data = Mock(side_effect=lambda addr, reg: {
        0xFF: 0x15,  # Part ID
        0x04: 0x05,  # Write ptr
        0x06: 0x00,  # Read ptr
    }.get(reg, 0x00))
    adapter.write_byte_data = Mock()
    # FIFO data: 6 bytes per sample (3 red + 3 IR)
    adapter.read_i2c_block_data = Mock(return_value=[0x01, 0x80, 0x40, 0x02, 0x60, 0x30] * 5)
    return adapter


# ========== SPI ADAPTER FIXTURES ==========

@pytest.fixture
def mock_spi_adapter():
    """Mock SPI adapter for ADS1263."""
    adapter = Mock()
    adapter.open = Mock()
    adapter.close = Mock()
    # Default: return device ID in register read response
    adapter.xfer2 = Mock(return_value=[0x00, 0x00, 0x01, 0x00, 0x80, 0x00])
    return adapter


# ========== UART ADAPTER FIXTURES ==========

@pytest.fixture
def mock_uart_adapter():
    """Mock UART adapter for LD2410."""
    adapter = Mock()
    adapter.write = Mock(return_value=10)
    adapter.flush = Mock()
    # Build a valid LD2410 data frame (header=4 + data_len=2 + type=1 + head=1 +
    # target_state=1 + move_dist=2 + move_energy=1 + still_dist=2 + still_energy=1 +
    # detect_dist=2 + padding + tail=4 = must be >= 23 bytes after header)
    frame = (
        b'\xF4\xF3\xF2\xF1'  # header (4 bytes)
        + b'\x0D\x00'          # data length (2 bytes)
        + b'\x02\xAA'          # data type + head byte (2 bytes)
        + b'\x03'              # target state: both (byte index 2 after header+len)
        + b'\x64\x00'          # move distance 100cm
        + b'\x32'              # move energy 50
        + b'\xC8\x00'          # still distance 200cm
        + b'\x28'              # still energy 40
        + b'\x96\x00'          # detect distance 150cm
        + b'\x00\x00\x00\x00\x00'  # padding to reach 23+ bytes
        + b'\xF8\xF7\xF6\xF5'  # tail
    )
    adapter.read = Mock(return_value=frame)
    adapter.readline = Mock(return_value=b'')
    type(adapter).in_waiting = PropertyMock(return_value=len(frame))
    return adapter


@pytest.fixture
def mock_uart_tfmini():
    """Mock UART adapter for TFmini-S."""
    adapter = Mock()
    adapter.write = Mock(return_value=4)
    adapter.flush = Mock()
    # Build valid TFmini-S frame: 0x59 0x59 dist_L dist_H str_L str_H temp_L temp_H checksum
    dist = 150  # 150cm
    strength = 300
    temp_raw = 2368  # ~40°C
    frame_bytes = [
        0x59, 0x59,
        dist & 0xFF, (dist >> 8) & 0xFF,
        strength & 0xFF, (strength >> 8) & 0xFF,
        temp_raw & 0xFF, (temp_raw >> 8) & 0xFF,
    ]
    checksum = sum(frame_bytes) & 0xFF
    frame_bytes.append(checksum)
    adapter.read = Mock(return_value=bytes(frame_bytes * 3))
    adapter.readline = Mock(return_value=b'')
    type(adapter).in_waiting = PropertyMock(return_value=27)
    return adapter


# ========== INFERENCE ADAPTER FIXTURES ==========

@pytest.fixture
def mock_inference_adapter():
    """Mock NN inference adapter."""
    adapter = Mock()
    adapter.load = Mock(return_value=True)
    adapter.predict = Mock(side_effect=lambda x: x * 0.95)  # Near-identity
    adapter.get_info = Mock(return_value={"backend": "mock", "loaded": True})
    return adapter


# ========== CONFIG FIXTURES ==========

@pytest.fixture
def bme680_config():
    return {"address": 0x76, "poll_rate_hz": 1.0, "timeout_ms": 1000}


@pytest.fixture
def mlx90640_config():
    return {"address": 0x33, "poll_rate_hz": 4.0, "timeout_ms": 2000}


@pytest.fixture
def as7265x_config():
    return {"address": 0x49, "poll_rate_hz": 2.0, "timeout_ms": 1500}


@pytest.fixture
def max30102_config():
    return {"address": 0x57, "poll_rate_hz": 25.0, "timeout_ms": 500}


@pytest.fixture
def ads1263_config():
    return {
        "bus": 0, "device": 0, "max_speed_hz": 1000000, "mode": 1,
        "channels": {
            "gas_mq2": {"positive_input": 0, "negative_input": 1},
            "gas_mq7": {"positive_input": 2, "negative_input": 3},
        }
    }


@pytest.fixture
def hlk_ld2410_config():
    return {"port": "/dev/ttyAMA0", "baud_rate": 115200}


@pytest.fixture
def tfmini_config():
    return {"port": "/dev/ttyUSB0", "baud_rate": 115200, "max_range_cm": 1200, "min_range_cm": 10}


@pytest.fixture
def agent_config():
    return {
        "llm_endpoint": "http://localhost:11434",
        "model_name": "qwen2.5:3b",
        "temperature": 0.1,
        "max_tokens": 512,
        "mission_mode": "patrol",
        "human_in_loop_threshold": "HIGH",
        "max_iterations": 2,
    }


@pytest.fixture
def mock_tool_caller():
    """Mock tool caller for agent tests."""
    def caller(name, args):
        return {"sensor_id": args.get("sensor_id", "test"), "value": 42.0}
    return caller


@pytest.fixture
def anomaly_event():
    """Sample anomaly event for agent tests."""
    return {
        "anomaly_score": 0.8,
        "affected_sensors": ["bme680"],
        "timestamp": "2026-01-01T00:00:00Z",
    }


@pytest.fixture
def anomaly_model_config():
    return {
        "model_path": "models/onnx/anomaly_lstm.onnx",
        "input_shape": [1, 256, 10],
        "output_shape": [1, 10],
        "confidence_threshold": 0.75,
        "window_size": 256,
    }


@pytest.fixture
def fusion_model_config():
    return {
        "model_path": "models/onnx/fusion_transformer.onnx",
        "input_shape": [1, 16, 64],
        "output_shape": [1, 512],
        "confidence_threshold": 0.80,
    }


@pytest.fixture
def sample_sensor_reading():
    from sensors.base import SensorReading
    return SensorReading(
        sensor_id="test_sensor_001",
        timestamp=datetime.now(timezone.utc),
        value={"temperature_c": 22.5, "humidity_rh": 45.0},
        unit="composite",
        confidence=0.95,
        metadata={"source": "test"},
    )


@pytest.fixture
def test_config_path(tmp_path):
    """Create a temporary test config file."""
    config_content = """
project_name: "Test Tricorder"
version: "1.0.0-test"
environment: "development"
sensors:
  i2c_devices:
    bme680:
      address: 118
      bus: 1
      enabled: true
      poll_rate_hz: 1.0
      timeout_ms: 1000
mcp_server:
  host: "127.0.0.1"
  port: 8000
  transport: "http"
  auth_enabled: false
  max_concurrent_tools: 10
logging:
  level: "DEBUG"
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  file_path: null
  max_bytes: 10485760
  backup_count: 0
"""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(config_content)
    return config_file


# ========== MQTT CONFIG FIXTURES ==========

@pytest.fixture
def mqtt_config():
    """MQTT publisher test configuration."""
    return {
        "host": "localhost",
        "port": 1883,
        "topic_prefix": "test/tricorder",
        "keepalive_s": 30,
        "qos": 1,
        "enabled": True,
    }


# ========== CONFIG MANAGER FIXTURES ==========

@pytest.fixture
def config_manager():
    """ConfigManager with admin enabled for testing."""
    from utils.config import ConfigManager, TricorderConfig

    config = TricorderConfig(
        admin={
            "enabled": True,
            "hmac_secret": "test-secret",
            "allowed_sections": ["ui", "logging", "feature_flags"],
        },
    )
    return ConfigManager(config)
