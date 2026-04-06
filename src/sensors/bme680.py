"""BME680 environmental sensor driver (temperature, humidity, pressure, VOC)."""

from datetime import datetime, timezone
from typing import Any, Dict
import logging

from sensors.base import (
    BaseSensor, SensorReading, SensorStatus,
    SensorInitializationError, SensorCommunicationError, SensorFactory,
)

logger = logging.getLogger(__name__)


class BME680Sensor(BaseSensor):
    """
    BME680 environmental sensor.

    Reads temperature, humidity, pressure, and gas resistance via I2C.
    Register addresses and chip ID are read from config.
    """

    DEFAULT_REGISTERS = {
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
    }

    DEFAULT_EXPECTED_CHIP_ID = 0x61
    DEFAULT_OVERSAMPLING = {
        "humidity": 0x01,       # 1x oversampling
        "temp_pressure": 0x25,  # temp 1x, pressure 1x, forced mode
    }
    DEFAULT_CONFIDENCE = 0.95
    DEFAULT_CALIBRATION = {
        "temp_divisor": 16384.0,
        "temp_scale": 40.0,
        "temp_offset": -10.0,
        "hum_divisor": 65535.0,
        "hum_scale": 100.0,
        "press_divisor": 16384.0,
        "press_scale": 300.0,
        "press_offset": 800.0,
        "gas_multiplier": 100,
    }

    def __init__(self, sensor_id: str, adapter: Any, config: Dict[str, Any]):
        super().__init__(sensor_id, adapter, config)
        self.address = config.get("address", 0x76)
        self.registers = config.get("registers", self.DEFAULT_REGISTERS)
        self.expected_chip_id = config.get("expected_chip_id", self.DEFAULT_EXPECTED_CHIP_ID)
        self.oversampling = config.get("oversampling", self.DEFAULT_OVERSAMPLING)
        self.calibration = config.get("calibration", self.DEFAULT_CALIBRATION)
        self.confidence = config.get("confidence", self.DEFAULT_CONFIDENCE)

    def initialize(self) -> bool:
        try:
            chip_id = self.adapter.read_byte_data(
                self.address, self.registers["chip_id_reg"]
            )
            if chip_id != self.expected_chip_id:
                raise SensorInitializationError(
                    f"BME680 chip ID mismatch: expected 0x{self.expected_chip_id:02X}, "
                    f"got 0x{chip_id:02X}"
                )
            # Configure humidity oversampling
            self.adapter.write_byte_data(
                self.address, self.registers["ctrl_hum"],
                self.oversampling["humidity"],
            )
            # Configure temp/pressure oversampling
            self.adapter.write_byte_data(
                self.address, self.registers["ctrl_meas"],
                self.oversampling["temp_pressure"],
            )
            self.status = SensorStatus.READY
            logger.info("%s initialized successfully", self.sensor_id)
            return True
        except SensorInitializationError as e:
            self._record_error(e)
            raise
        except Exception as e:
            self._record_error(e)
            raise SensorInitializationError(f"Failed to initialize BME680: {e}") from e

    def read(self) -> SensorReading:
        try:
            self.status = SensorStatus.READING

            raw_temp = self.adapter.read_i2c_block_data(
                self.address, self.registers["temp_msb"], 3
            )
            raw_hum = self.adapter.read_i2c_block_data(
                self.address, self.registers["hum_msb"], 2
            )
            raw_press = self.adapter.read_i2c_block_data(
                self.address, self.registers["press_msb"], 3
            )
            raw_gas = self.adapter.read_i2c_block_data(
                self.address, self.registers["gas_msb"], 2
            )

            temp_adc = (raw_temp[0] << 12) | (raw_temp[1] << 4) | (raw_temp[2] >> 4)
            hum_adc = (raw_hum[0] << 8) | raw_hum[1]
            press_adc = (raw_press[0] << 12) | (raw_press[1] << 4) | (raw_press[2] >> 4)
            gas_adc = (raw_gas[0] << 2) | (raw_gas[1] >> 6)

            # Simplified conversion (real driver would use calibration coefficients)
            cal = self.calibration
            temp_c = temp_adc / cal["temp_divisor"] * cal["temp_scale"] + cal["temp_offset"]
            humidity_rh = hum_adc / cal["hum_divisor"] * cal["hum_scale"]
            pressure_hpa = press_adc / cal["press_divisor"] * cal["press_scale"] + cal["press_offset"]
            gas_resistance_ohm = max(1, gas_adc) * cal["gas_multiplier"]

            reading = SensorReading(
                sensor_id=self.sensor_id,
                timestamp=datetime.now(timezone.utc),
                value={
                    "temperature_c": round(temp_c, 2),
                    "humidity_rh": round(humidity_rh, 2),
                    "pressure_hpa": round(pressure_hpa, 2),
                    "gas_resistance_ohm": gas_resistance_ohm,
                },
                unit="composite",
                confidence=self.confidence,
                metadata={"i2c_address": f"0x{self.address:02X}"},
            )
            self._record_reading(reading)
            return reading
        except Exception as e:
            self._record_error(e)
            raise SensorCommunicationError(f"BME680 read failed: {e}") from e

    def calibrate(self, **kwargs: Any) -> bool:
        self.status = SensorStatus.CALIBRATING
        logger.info("%s calibration triggered (baseline recalc)", self.sensor_id)
        self.status = SensorStatus.READY
        return True


SensorFactory.register("bme680", BME680Sensor)
