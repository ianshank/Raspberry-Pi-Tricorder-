"""HLK-LD2410 24GHz mmWave radar sensor driver (UART)."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
import struct
import logging

from sensors.base import (
    BaseSensor, SensorReading,
    SensorInitializationError, SensorCommunicationError, SensorFactory,
)
from utils.constants import DEFAULT_UART_BAUD_RATE, UART_READ_BUFFER_SIZE
from utils.platform import default_uart_port

logger = logging.getLogger(__name__)


class HLKLD2410Sensor(BaseSensor):
    """
    HLK-LD2410 mmWave presence/motion radar.

    Communicates via UART with binary protocol.
    Detects stationary and moving targets with distance and energy.
    """

    FRAME_HEADER = b'\xF4\xF3\xF2\xF1'
    FRAME_TAIL = b'\xF8\xF7\xF6\xF5'
    CMD_HEADER = b'\xFD\xFC\xFB\xFA'
    CMD_TAIL = b'\x04\x03\x02\x01'

    DEFAULT_CONFIG = {
        "max_gate": 8,
        "max_move_gate": 8,
        "max_still_gate": 8,
        "timeout_s": 5,
    }
    DEFAULT_CONFIDENCE = 0.88
    DEFAULT_COMMAND_WORDS = {
        "enable_config": 0x00FF,
        "read_firmware": 0x0000,
        "end_config": 0x00FE,
    }

    def __init__(self, sensor_id: str, adapter: Any, config: Dict[str, Any]):
        super().__init__(sensor_id, adapter, config)
        self.port = config.get("port", default_uart_port())
        self.baud_rate = config.get("baud_rate", DEFAULT_UART_BAUD_RATE)
        self.max_gate = config.get("max_gate", self.DEFAULT_CONFIG["max_gate"])
        self.timeout = config.get("timeout_s", self.DEFAULT_CONFIG["timeout_s"])
        self.command_words = config.get("command_words", self.DEFAULT_COMMAND_WORDS)
        self.confidence = config.get("confidence", self.DEFAULT_CONFIDENCE)

    def _send_command(self, cmd_word: int, data: bytes = b'') -> Optional[bytes]:
        """Send command frame and read response."""
        data_len = len(data) + 2
        frame = (
            self.CMD_HEADER
            + struct.pack('<H', data_len)
            + struct.pack('<H', cmd_word)
            + data
            + self.CMD_TAIL
        )
        self.adapter.write(frame)
        self.adapter.flush()
        response = self.adapter.read(64)
        return response if response else None

    def _parse_data_frame(self, frame: bytes) -> Optional[Dict[str, Any]]:
        """Parse a data reporting frame."""
        if len(frame) < 23:
            return None

        # Find frame header
        idx = frame.find(self.FRAME_HEADER)
        if idx < 0 or idx + 23 > len(frame):
            return None

        data = frame[idx + 4:]  # Skip header
        if len(data) < 19:
            return None

        # Parse target data
        target_state = data[2] if len(data) > 2 else 0
        move_distance = struct.unpack_from('<H', data, 3)[0] if len(data) > 4 else 0
        move_energy = data[5] if len(data) > 5 else 0
        still_distance = struct.unpack_from('<H', data, 6)[0] if len(data) > 7 else 0
        still_energy = data[8] if len(data) > 8 else 0
        detect_distance = struct.unpack_from('<H', data, 9)[0] if len(data) > 10 else 0

        state_map = {0: "no_target", 1: "moving", 2: "stationary", 3: "both"}

        return {
            "target_state": state_map.get(target_state, "unknown"),
            "moving_target_distance_cm": move_distance,
            "moving_target_energy": move_energy,
            "stationary_target_distance_cm": still_distance,
            "stationary_target_energy": still_energy,
            "detection_distance_cm": detect_distance,
        }

    def _do_initialize(self) -> bool:
        # Enable configuration mode
        response = self._send_command(
            self.command_words["enable_config"], b'\x01\x00',
        )
        if response is None:
            raise SensorInitializationError("No response from LD2410")

        # Read firmware version
        fw_response = self._send_command(self.command_words["read_firmware"])
        logger.debug("%s firmware response: %s",
                     self.sensor_id,
                     fw_response.hex() if fw_response else "none")

        # End configuration mode
        self._send_command(self.command_words["end_config"])

        logger.info("%s initialized", self.sensor_id)
        return True

    def _do_read(self) -> SensorReading:
        # Read data frame from UART
        raw_data = self.adapter.read(UART_READ_BUFFER_SIZE)
        if not raw_data:
            raise SensorCommunicationError("No data from LD2410")

        parsed = self._parse_data_frame(raw_data)
        if parsed is None:
            raise SensorCommunicationError("Invalid frame from LD2410")

        return SensorReading(
            sensor_id=self.sensor_id,
            timestamp=datetime.now(timezone.utc),
            value=parsed,
            unit="composite",
            confidence=self.confidence,
            metadata={"port": self.port},
        )


SensorFactory.register("hlk_ld2410", HLKLD2410Sensor)
