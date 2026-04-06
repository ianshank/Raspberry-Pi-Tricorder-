"""ADS1263 32-bit precision ADC sensor driver (SPI)."""

from datetime import datetime, timezone
from typing import Any, Dict
import logging

from sensors.base import (
    BaseSensor, SensorReading, SensorStatus,
    SensorInitializationError, SensorCommunicationError, SensorFactory,
)

logger = logging.getLogger(__name__)


class ADS1263Sensor(BaseSensor):
    """
    ADS1263 32-bit precision ADC.

    Communicates via SPI. Supports differential and single-ended measurements.
    Channel configuration is loaded from config (no hardcoded channel assignments).
    """

    DEFAULT_COMMANDS = {
        "reset": 0x06,
        "start1": 0x08,
        "stop1": 0x0A,
        "rdata1": 0x12,
        "rreg": 0x20,
        "wreg": 0x40,
    }
    DEFAULT_REGISTERS = {
        "id": 0x00,
        "power": 0x01,
        "interface": 0x02,
        "mode0": 0x03,
        "mode1": 0x04,
        "mode2": 0x05,
        "inpmux": 0x06,
        "ofcal0": 0x07,
        "fscal0": 0x0A,
        "ref": 0x0F,
    }
    DEFAULT_EXPECTED_ID = 0x01
    VREF = 2.5  # Internal reference voltage
    DEFAULT_CONFIDENCE = 0.98
    DEFAULT_INIT_CONFIG = {
        "ref_value": 0x19,    # Internal reference enabled
        "filter_value": 0x04,  # Sinc1 filter, 20 SPS
    }

    def __init__(self, sensor_id: str, adapter: Any, config: Dict[str, Any]):
        super().__init__(sensor_id, adapter, config)
        self.bus = config.get("bus", 0)
        self.device = config.get("device", 0)
        self.max_speed_hz = config.get("max_speed_hz", 1000000)
        self.mode = config.get("mode", 1)
        self.commands = config.get("commands", self.DEFAULT_COMMANDS)
        self.registers = config.get("registers", self.DEFAULT_REGISTERS)
        self.expected_id = config.get("expected_id", self.DEFAULT_EXPECTED_ID)
        self.vref = config.get("vref", self.VREF)
        self.channels = config.get("channels", {})
        self.init_config = config.get("init_config", self.DEFAULT_INIT_CONFIG)
        self.confidence = config.get("confidence", self.DEFAULT_CONFIDENCE)

    def _read_register(self, reg: int) -> int:
        cmd = [self.commands["rreg"] | reg, 0x00, 0x00]
        response = self.adapter.xfer2(cmd)
        return response[2] if len(response) > 2 else 0

    def _write_register(self, reg: int, value: int) -> None:
        cmd = [self.commands["wreg"] | reg, 0x00, value]
        self.adapter.xfer2(cmd)

    def initialize(self) -> bool:
        try:
            self.adapter.open(self.bus, self.device)

            # Send reset command
            self.adapter.xfer2([self.commands["reset"]])

            # Read device ID
            device_id = self._read_register(self.registers["id"])
            if (device_id & 0x1F) != self.expected_id:
                raise SensorInitializationError(
                    f"ADS1263 ID mismatch: expected 0x{self.expected_id:02X}, "
                    f"got 0x{device_id:02X}"
                )

            # Configure: internal reference, filter mode
            self._write_register(self.registers["ref"], self.init_config["ref_value"])
            self._write_register(self.registers["mode2"], self.init_config["filter_value"])

            # Start conversion
            self.adapter.xfer2([self.commands["start1"]])

            self.status = SensorStatus.READY
            logger.info("%s initialized (ID: 0x%02X)", self.sensor_id, device_id)
            return True
        except SensorInitializationError as e:
            self._record_error(e)
            raise
        except Exception as e:
            self._record_error(e)
            raise SensorInitializationError(f"ADS1263 init failed: {e}") from e

    def read_channel(self, positive_input: int, negative_input: int) -> float:
        """Read a single differential channel pair."""
        mux_value = (positive_input << 4) | negative_input
        self._write_register(self.registers["inpmux"], mux_value)

        # Trigger and read conversion
        self.adapter.xfer2([self.commands["start1"]])
        cmd = [self.commands["rdata1"]] + [0x00] * 5
        response = self.adapter.xfer2(cmd)

        # Parse 32-bit result (bytes 1-4, skip status byte)
        if len(response) >= 5:
            raw = (
                (response[1] << 24)
                | (response[2] << 16)
                | (response[3] << 8)
                | response[4]
            )
            if raw > 0x7FFFFFFF:
                raw -= 0x100000000
            voltage = raw * self.vref / 0x7FFFFFFF
        else:
            voltage = 0.0

        return round(voltage, 6)

    def read(self) -> SensorReading:
        try:
            self.status = SensorStatus.READING

            channel_readings: Dict[str, float] = {}
            for name, ch_config in self.channels.items():
                voltage = self.read_channel(
                    ch_config.get("positive_input", 0),
                    ch_config.get("negative_input", 1),
                )
                channel_readings[name] = voltage

            reading = SensorReading(
                sensor_id=self.sensor_id,
                timestamp=datetime.now(timezone.utc),
                value={
                    "channels": channel_readings,
                    "channel_count": len(channel_readings),
                    "vref": self.vref,
                },
                unit="volts",
                confidence=self.confidence,
                metadata={"spi_bus": self.bus, "spi_device": self.device},
            )
            self._record_reading(reading)
            return reading
        except Exception as e:
            self._record_error(e)
            raise SensorCommunicationError(f"ADS1263 read failed: {e}") from e

    def reset(self) -> bool:
        try:
            self.adapter.xfer2([self.commands["reset"]])
            self.status = SensorStatus.UNINITIALIZED
            logger.info("%s reset", self.sensor_id)
            return True
        except Exception as e:
            logger.error("%s reset failed: %s", self.sensor_id, e)
            return False


SensorFactory.register("ads1263", ADS1263Sensor)
