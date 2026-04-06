"""MAX30102 SpO2/heart rate sensor driver."""

from datetime import datetime, timezone
from typing import Any, Dict
import logging

from sensors.base import (
    BaseSensor, SensorReading, SensorStatus,
    SensorInitializationError, SensorCommunicationError, SensorFactory,
)

logger = logging.getLogger(__name__)


class MAX30102Sensor(BaseSensor):
    """
    MAX30102 pulse oximetry and heart rate sensor.

    Reads red and IR LED data via I2C FIFO interface.
    """

    DEFAULT_REGISTERS = {
        "part_id_reg": 0xFF,
        "rev_id_reg": 0xFE,
        "mode_config": 0x09,
        "spo2_config": 0x0A,
        "led1_pulse_amp": 0x0C,  # Red LED
        "led2_pulse_amp": 0x0D,  # IR LED
        "fifo_write_ptr": 0x04,
        "fifo_read_ptr": 0x06,
        "fifo_data_reg": 0x07,
        "fifo_config": 0x08,
        "int_status1": 0x00,
    }
    DEFAULT_EXPECTED_PART_ID = 0x15
    DEFAULT_DEVICE_CONFIG = {
        "reset_value": 0x40,
        "spo2_mode": 0x03,         # Red + IR LEDs
        "spo2_config": 0x27,       # 4096 ADC range, 100 SPS, 18-bit
        "fifo_sample_avg": 0x40,   # Sample averaging = 4
    }
    DEFAULT_SPO2_CALIBRATION = {
        "intercept": 110,
        "slope": 25,
    }
    DEFAULT_CONFIDENCE = 0.85
    DEFAULT_HR_BOUNDS = {"min_bpm": 40, "max_bpm": 200}

    def __init__(self, sensor_id: str, adapter: Any, config: Dict[str, Any]):
        super().__init__(sensor_id, adapter, config)
        self.address = config.get("address", 0x57)
        self.registers = config.get("registers", self.DEFAULT_REGISTERS)
        self.expected_part_id = config.get(
            "expected_part_id", self.DEFAULT_EXPECTED_PART_ID
        )
        self.led_amplitude = config.get("led_amplitude", 0x24)  # ~7mA
        self.sample_rate = config.get("sample_rate", 100)
        self.device_config = config.get("device_config", self.DEFAULT_DEVICE_CONFIG)
        self.spo2_calibration = config.get("spo2_calibration", self.DEFAULT_SPO2_CALIBRATION)
        self.confidence = config.get("confidence", self.DEFAULT_CONFIDENCE)
        self.hr_bounds = config.get("hr_bounds", self.DEFAULT_HR_BOUNDS)

    def initialize(self) -> bool:
        try:
            part_id = self.adapter.read_byte_data(
                self.address, self.registers["part_id_reg"]
            )
            if part_id != self.expected_part_id:
                raise SensorInitializationError(
                    f"MAX30102 part ID mismatch: expected 0x{self.expected_part_id:02X}, "
                    f"got 0x{part_id:02X}"
                )

            # Reset device
            self.adapter.write_byte_data(
                self.address, self.registers["mode_config"],
                self.device_config["reset_value"],
            )
            # SpO2 mode (red + IR)
            self.adapter.write_byte_data(
                self.address, self.registers["mode_config"],
                self.device_config["spo2_mode"],
            )
            # SpO2 config: ADC range, sample rate, resolution
            self.adapter.write_byte_data(
                self.address, self.registers["spo2_config"],
                self.device_config["spo2_config"],
            )
            # LED amplitudes
            self.adapter.write_byte_data(
                self.address, self.registers["led1_pulse_amp"], self.led_amplitude
            )
            self.adapter.write_byte_data(
                self.address, self.registers["led2_pulse_amp"], self.led_amplitude
            )
            # FIFO config: sample averaging
            self.adapter.write_byte_data(
                self.address, self.registers["fifo_config"],
                self.device_config["fifo_sample_avg"],
            )

            self.status = SensorStatus.READY
            logger.info("%s initialized (part ID: 0x%02X)", self.sensor_id, part_id)
            return True
        except SensorInitializationError as e:
            self._record_error(e)
            raise
        except Exception as e:
            self._record_error(e)
            raise SensorInitializationError(f"MAX30102 init failed: {e}") from e

    def read(self) -> SensorReading:
        try:
            self.status = SensorStatus.READING

            # Read FIFO pointers to determine available samples
            write_ptr = self.adapter.read_byte_data(
                self.address, self.registers["fifo_write_ptr"]
            )
            read_ptr = self.adapter.read_byte_data(
                self.address, self.registers["fifo_read_ptr"]
            )
            num_samples = (write_ptr - read_ptr) & 0x1F
            if num_samples == 0:
                num_samples = 1

            # Read FIFO data (6 bytes per sample: 3 red + 3 IR)
            fifo_data = self.adapter.read_i2c_block_data(
                self.address, self.registers["fifo_data_reg"], min(num_samples * 6, 32)
            )

            red_values = []
            ir_values = []
            for i in range(0, len(fifo_data) - 5, 6):
                red = ((fifo_data[i] & 0x03) << 16) | (fifo_data[i + 1] << 8) | fifo_data[i + 2]
                ir = ((fifo_data[i + 3] & 0x03) << 16) | (fifo_data[i + 4] << 8) | fifo_data[i + 5]
                red_values.append(red)
                ir_values.append(ir)

            # Simplified SpO2 / HR estimation
            avg_red = sum(red_values) / max(len(red_values), 1)
            avg_ir = sum(ir_values) / max(len(ir_values), 1)
            ratio = avg_red / max(avg_ir, 1)
            spo2_cal = self.spo2_calibration
            spo2_estimate = max(0, min(100, spo2_cal["intercept"] - spo2_cal["slope"] * ratio))
            hr_estimate = max(
                self.hr_bounds["min_bpm"],
                min(self.hr_bounds["max_bpm"], len(red_values) * 60 / max(num_samples, 1)),
            )

            reading = SensorReading(
                sensor_id=self.sensor_id,
                timestamp=datetime.now(timezone.utc),
                value={
                    "spo2_percent": round(spo2_estimate, 1),
                    "heart_rate_bpm": round(hr_estimate, 1),
                    "red_avg": round(avg_red, 1),
                    "ir_avg": round(avg_ir, 1),
                    "samples_read": len(red_values),
                },
                unit="composite",
                confidence=self.confidence,
                metadata={"i2c_address": f"0x{self.address:02X}"},
            )
            self._record_reading(reading)
            return reading
        except Exception as e:
            self._record_error(e)
            raise SensorCommunicationError(f"MAX30102 read failed: {e}") from e


SensorFactory.register("max30102", MAX30102Sensor)
