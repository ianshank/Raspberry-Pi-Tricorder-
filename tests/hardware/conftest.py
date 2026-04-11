"""Hardware test fixtures and custom markers for on-device sensor testing."""

from __future__ import annotations

import importlib
import logging
import sys
from typing import Any, Dict

import pytest

# Skip entire hardware test directory on non-Linux platforms
pytestmark = pytest.mark.skipif(
    sys.platform != "linux",
    reason="Hardware tests require Linux (Raspberry Pi)",
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sensor-to-bus-module mapping
# ---------------------------------------------------------------------------

SENSOR_MODULES: Dict[str, str] = {
    "bme680": "smbus2",
    "bme280": "smbus2",
    "bno055": "smbus2",
    "ina219": "smbus2",
    "ads1115": "smbus2",
    "mcp3008": "spidev",
    "max31855": "spidev",
    "gps": "serial",
    "pmsa003i": "smbus2",
}


def _bus_available(module_name: str) -> bool:
    """Return True if the given bus module can be imported."""
    try:
        importlib.import_module(module_name)
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Custom marker: @pytest.mark.sensor_required("sensor_id")
# ---------------------------------------------------------------------------

def pytest_configure(config: Any) -> None:
    """Register the ``sensor_required`` and ``hardware`` markers."""
    config.addinivalue_line(
        "markers",
        "sensor_required(sensor_id): skip test unless the sensor's bus module is available",
    )
    config.addinivalue_line(
        "markers",
        "hardware: marks tests that require physical hardware",
    )


def pytest_collection_modifyitems(config: Any, items: list) -> None:  # type: ignore[type-arg]
    """Auto-skip tests whose required sensor bus module is not importable."""
    for item in items:
        for marker in item.iter_markers("sensor_required"):
            sensor_id: str = marker.args[0]
            bus_module = SENSOR_MODULES.get(sensor_id)
            if bus_module is None:
                item.add_marker(
                    pytest.mark.skip(reason=f"Unknown sensor '{sensor_id}' — not in SENSOR_MODULES")
                )
            elif not _bus_available(bus_module):
                item.add_marker(
                    pytest.mark.skip(
                        reason=f"Bus module '{bus_module}' for sensor '{sensor_id}' not available"
                    )
                )


# ---------------------------------------------------------------------------
# Hardware adapter fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def real_i2c_adapter():
    """Provide a real SMBus I2C adapter (bus 1) or skip."""
    if not _bus_available("smbus2"):
        pytest.skip("smbus2 not available — no I2C hardware")
    import smbus2  # type: ignore[import-untyped]

    bus = smbus2.SMBus(1)
    yield bus
    bus.close()


@pytest.fixture()
def real_spi_adapter():
    """Provide a real SpiDev adapter (bus 0, device 0) or skip."""
    if not _bus_available("spidev"):
        pytest.skip("spidev not available — no SPI hardware")
    import spidev  # type: ignore[import-untyped]

    spi = spidev.SpiDev()
    spi.open(0, 0)
    spi.max_speed_hz = 1_000_000
    yield spi
    spi.close()


@pytest.fixture()
def real_uart_adapter():
    """Provide a real serial/UART adapter or skip."""
    if not _bus_available("serial"):
        pytest.skip("pyserial not available — no UART hardware")
    import serial  # type: ignore[import-untyped]

    port = serial.Serial("/dev/ttyAMA0", baudrate=9600, timeout=1)
    yield port
    port.close()


@pytest.fixture()
def bme680_config() -> Dict[str, Any]:
    """Default BME680 configuration for hardware tests."""
    return {
        "address": 0x76,
        "registers": {
            "chip_id_reg": 0xD0,
            "ctrl_gas": 0x71,
            "ctrl_hum": 0x72,
            "ctrl_meas": 0x74,
            "status_reg": 0x73,
            "temp_msb": 0x22,
            "temp_lsb": 0x23,
            "temp_xlsb": 0x24,
            "press_msb": 0x1F,
            "hum_msb": 0x25,
            "hum_lsb": 0x26,
            "gas_msb": 0x2A,
            "gas_lsb": 0x2B,
        },
        "expected_chip_id": 0x61,
    }
