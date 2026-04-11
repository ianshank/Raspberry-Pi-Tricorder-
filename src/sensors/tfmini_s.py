"""TFmini-S LiDAR time-of-flight distance sensor driver (UART)."""

import logging
import struct
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sensors.base import (
    BaseSensor,
    SensorCommunicationError,
    SensorFactory,
    SensorReading,
)
from utils.constants import DEFAULT_UART_BAUD_RATE
from utils.platform import default_uart_port

logger = logging.getLogger(__name__)


class TFMiniSSensor(BaseSensor):
    """
    TFmini-S LiDAR Time-of-Flight ranging sensor.

    Communicates via UART. Outputs 9-byte data frames at configurable rate.
    """

    FRAME_HEADER = 0x59
    FRAME_LENGTH = 9
    DEFAULT_COMMANDS = {
        "version_query": bytes([0x5A, 0x04, 0x01, 0x5F]),
        "output_standard": bytes([0x5A, 0x05, 0x05, 0x01, 0x65]),
    }
    DEFAULT_TEMP_CONVERSION = {
        "divisor": 8.0,
        "offset": 256.0,
    }
    DEFAULT_CONFIDENCE = 0.95
    LOW_CONFIDENCE = 0.3

    def __init__(self, sensor_id: str, adapter: Any, config: Dict[str, Any]):
        super().__init__(sensor_id, adapter, config)
        self.port = config.get("port", default_uart_port())
        self.baud_rate = config.get("baud_rate", DEFAULT_UART_BAUD_RATE)
        self.max_range_cm = config.get("max_range_cm", 1200)
        self.min_range_cm = config.get("min_range_cm", 10)
        self.commands = config.get("commands", self.DEFAULT_COMMANDS)
        self.temp_conversion = config.get("temp_conversion", self.DEFAULT_TEMP_CONVERSION)
        self.confidence = config.get("confidence", self.DEFAULT_CONFIDENCE)
        self.low_confidence = config.get("low_confidence", self.LOW_CONFIDENCE)

    def _parse_frame(self, data: bytes) -> Optional[Dict[str, Any]]:
        """Parse a TFmini-S 9-byte data frame."""
        if len(data) < self.FRAME_LENGTH:
            return None

        # Find double-header 0x59 0x59
        for i in range(len(data) - self.FRAME_LENGTH + 1):
            if data[i] == self.FRAME_HEADER and data[i + 1] == self.FRAME_HEADER:
                frame = data[i:i + self.FRAME_LENGTH]

                # Verify checksum
                checksum = sum(frame[:8]) & 0xFF
                if checksum != frame[8]:
                    continue

                distance_cm = struct.unpack_from('<H', frame, 2)[0]
                strength = struct.unpack_from('<H', frame, 4)[0]
                temperature_raw = struct.unpack_from('<H', frame, 6)[0]
                temperature_c = (temperature_raw / self.temp_conversion["divisor"]
                                 - self.temp_conversion["offset"])

                return {
                    "distance_cm": distance_cm,
                    "signal_strength": strength,
                    "temperature_c": round(temperature_c, 1),
                    "valid": self.min_range_cm <= distance_cm <= self.max_range_cm,
                }
        return None

    def _do_initialize(self) -> bool:
        # Send version query command
        self.adapter.write(self.commands["version_query"])
        self.adapter.flush()
        response = self.adapter.read(32)

        if not response:
            logger.warning("%s no version response, continuing anyway", self.sensor_id)

        # Set output mode to standard (9-byte frames)
        self.adapter.write(self.commands["output_standard"])
        self.adapter.flush()

        logger.info("%s initialized", self.sensor_id)
        return True

    def _do_read(self) -> SensorReading:
        raw_data = self.adapter.read(self.FRAME_LENGTH * 3)
        if not raw_data:
            raise SensorCommunicationError("No data from TFmini-S")

        parsed = self._parse_frame(raw_data)
        if parsed is None:
            raise SensorCommunicationError("Invalid frame from TFmini-S")

        confidence = self.confidence if parsed["valid"] else self.low_confidence

        return SensorReading(
            sensor_id=self.sensor_id,
            timestamp=datetime.now(timezone.utc),
            value=parsed,
            unit="cm",
            confidence=confidence,
            metadata={"port": self.port},
        )


SensorFactory.register("tfmini_s", TFMiniSSensor)
