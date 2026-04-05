"""AS7265x 18-channel spectral sensor driver."""

from datetime import datetime, timezone
from typing import Any, Dict, List
import logging

from sensors.base import (
    BaseSensor, SensorReading, SensorStatus,
    SensorInitializationError, SensorCommunicationError, SensorFactory,
)

logger = logging.getLogger(__name__)

SPECTRAL_CHANNEL_COUNT = 18


class AS7265xSensor(BaseSensor):
    """
    AS7265x Triad Spectroscopy Sensor (18 channels across UV/VIS/NIR).

    Uses virtual register interface over I2C.
    """

    DEFAULT_REGISTERS = {
        "status_reg": 0x00,
        "write_reg": 0x01,
        "read_reg": 0x02,
        "hw_version": 0x00,
        "device_type": 0x00,
        "control_setup": 0x04,
        "integration_time": 0x05,
        "led_control": 0x07,
    }
    DEFAULT_HW_VERSION = 0x40
    CHANNEL_WAVELENGTHS_NM = [
        410, 435, 460, 485, 510, 535,  # UV
        560, 585, 610, 645, 680, 705,  # VIS
        730, 760, 810, 860, 900, 940,  # NIR
    ]

    def __init__(self, sensor_id: str, adapter: Any, config: Dict[str, Any]):
        super().__init__(sensor_id, adapter, config)
        self.address = config.get("address", 0x49)
        self.registers = config.get("registers", self.DEFAULT_REGISTERS)
        self.expected_hw_version = config.get(
            "expected_hw_version", self.DEFAULT_HW_VERSION
        )
        self.channel_count = config.get("channel_count", SPECTRAL_CHANNEL_COUNT)
        self.wavelengths = config.get(
            "wavelengths_nm", self.CHANNEL_WAVELENGTHS_NM
        )

    def _virtual_read(self, virtual_reg: int) -> int:
        """Read from virtual register via status/write/read interface."""
        # Wait for ready
        status = self.adapter.read_byte_data(
            self.address, self.registers["status_reg"]
        )
        # Write virtual register address
        self.adapter.write_byte_data(
            self.address, self.registers["write_reg"], virtual_reg
        )
        # Read result
        return self.adapter.read_byte_data(
            self.address, self.registers["read_reg"]
        )

    def initialize(self) -> bool:
        try:
            hw_version = self._virtual_read(self.registers["hw_version"])
            if (hw_version & 0xF0) != (self.expected_hw_version & 0xF0):
                raise SensorInitializationError(
                    f"AS7265x HW version mismatch: expected 0x{self.expected_hw_version:02X}, "
                    f"got 0x{hw_version:02X}"
                )

            # Set integration time
            self.adapter.write_byte_data(
                self.address, self.registers["write_reg"],
                self.registers["integration_time"]
            )
            self.adapter.write_byte_data(
                self.address, self.registers["write_reg"], 50  # ~50ms integration
            )

            self.status = SensorStatus.READY
            logger.info("%s initialized (HW: 0x%02X)", self.sensor_id, hw_version)
            return True
        except SensorInitializationError:
            self._record_error(SensorInitializationError("HW version mismatch"))
            raise
        except Exception as e:
            self._record_error(e)
            raise SensorInitializationError(f"AS7265x init failed: {e}") from e

    def read(self) -> SensorReading:
        try:
            self.status = SensorStatus.READING

            # Read calibrated channel data (6 bytes per device x 3 devices = 18 channels)
            channels: List[float] = []
            for i in range(self.channel_count):
                # Each channel is 2 bytes (MSB, LSB) from calibrated data registers
                raw_data = self.adapter.read_i2c_block_data(
                    self.address, 0x08 + i * 2, 2
                )
                raw_value = (raw_data[0] << 8) | raw_data[1]
                # Convert to calibrated float (simplified)
                calibrated = raw_value / 65535.0 * 100.0
                channels.append(round(calibrated, 4))

            # Build wavelength-mapped result
            spectral_data = {}
            for i, wavelength in enumerate(self.wavelengths[:len(channels)]):
                spectral_data[f"{wavelength}nm"] = channels[i]

            reading = SensorReading(
                sensor_id=self.sensor_id,
                timestamp=datetime.now(timezone.utc),
                value={
                    "spectral_channels": spectral_data,
                    "channel_count": len(channels),
                    "raw_values": channels,
                },
                unit="relative_intensity",
                confidence=0.92,
                metadata={"i2c_address": f"0x{self.address:02X}"},
            )
            self._record_reading(reading)
            return reading
        except Exception as e:
            self._record_error(e)
            raise SensorCommunicationError(f"AS7265x read failed: {e}") from e


SensorFactory.register("as7265x", AS7265xSensor)
