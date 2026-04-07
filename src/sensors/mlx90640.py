"""MLX90640 32x24 thermal camera sensor driver."""

from datetime import datetime, timezone
from typing import Any, Dict
import logging

from sensors.base import (
    BaseSensor, SensorReading, SensorFactory,
)

logger = logging.getLogger(__name__)

FRAME_ROWS = 24
FRAME_COLS = 32


class MLX90640Sensor(BaseSensor):
    """
    MLX90640 far-infrared thermal sensor array (32x24 pixels).

    Reads thermal frame data via I2C. Returns flattened pixel array.
    """

    DEFAULT_REGISTERS = {
        "status_reg": 0x8000,
        "control_reg": 0x800D,
        "device_id_reg": 0x2407,
    }
    DEFAULT_EXPECTED_DEVICE_ID_MASK = 0x00FF
    DEFAULT_REFRESH_RATE_CMD = [0x09, 0x01]  # 4 Hz refresh rate
    DEFAULT_I2C_CHUNK_SIZE = 32
    DEFAULT_TEMP_SCALE_FACTOR = 0.02
    DEFAULT_CONFIDENCE = 0.90

    def __init__(self, sensor_id: str, adapter: Any, config: Dict[str, Any]):
        super().__init__(sensor_id, adapter, config)
        self.address = config.get("address", 0x33)
        self.registers = config.get("registers", self.DEFAULT_REGISTERS)
        self.frame_rows = config.get("frame_rows", FRAME_ROWS)
        self.frame_cols = config.get("frame_cols", FRAME_COLS)
        self.refresh_rate_cmd = config.get("refresh_rate_cmd", self.DEFAULT_REFRESH_RATE_CMD)
        self.i2c_chunk_size = config.get("i2c_chunk_size", self.DEFAULT_I2C_CHUNK_SIZE)
        self.temp_scale_factor = config.get("temp_scale_factor", self.DEFAULT_TEMP_SCALE_FACTOR)
        self.confidence = config.get("confidence", self.DEFAULT_CONFIDENCE)

    def _do_initialize(self) -> bool:
        # Read device ID (lower byte check)
        id_bytes = self.adapter.read_i2c_block_data(
            self.address, self.registers["device_id_reg"] & 0xFF, 2
        )
        device_id = (id_bytes[0] << 8) | id_bytes[1]
        logger.debug("%s device ID: 0x%04X", self.sensor_id, device_id)

        # Set refresh rate via control register
        self.adapter.write_i2c_block_data(
            self.address,
            self.registers["control_reg"] & 0xFF,
            self.refresh_rate_cmd,
        )
        logger.info("%s initialized successfully", self.sensor_id)
        return True

    def _do_read(self) -> SensorReading:
        pixel_count = self.frame_rows * self.frame_cols

        # Read raw frame data in chunks (I2C block read size configurable)
        raw_bytes = []
        chunk_size = self.i2c_chunk_size
        for offset in range(0, pixel_count * 2, chunk_size):
            reg = (self.registers["status_reg"] + offset) & 0xFF
            length = min(chunk_size, pixel_count * 2 - offset)
            chunk = self.adapter.read_i2c_block_data(
                self.address, reg, length
            )
            raw_bytes.extend(chunk)

        # Convert raw bytes to temperature values (simplified)
        pixels = []
        for i in range(0, min(len(raw_bytes), pixel_count * 2), 2):
            raw = (raw_bytes[i] << 8) | raw_bytes[i + 1]
            if raw > 32767:
                raw -= 65536
            temp_c = raw * self.temp_scale_factor
            pixels.append(round(temp_c, 2))

        # Pad if we got fewer pixels than expected
        while len(pixels) < pixel_count:
            pixels.append(0.0)

        return SensorReading(
            sensor_id=self.sensor_id,
            timestamp=datetime.now(timezone.utc),
            value={
                "thermal_frame": pixels[:pixel_count],
                "rows": self.frame_rows,
                "cols": self.frame_cols,
                "min_temp_c": min(pixels[:pixel_count]),
                "max_temp_c": max(pixels[:pixel_count]),
                "avg_temp_c": round(
                    sum(pixels[:pixel_count]) / pixel_count, 2
                ),
            },
            unit="celsius",
            confidence=self.confidence,
            metadata={"i2c_address": f"0x{self.address:02X}"},
        )


SensorFactory.register("mlx90640", MLX90640Sensor)
