"""Sensor manager for orchestrating all sensor instances."""

from typing import Any, Dict, List, Optional
import logging

from sensors.base import BaseSensor, SensorFactory, SensorReading, SensorStatus

logger = logging.getLogger(__name__)


class SensorManager:
    """
    Manages lifecycle of all sensor instances.

    Creates sensors from config via SensorFactory, provides
    unified interface for reading, diagnostics, and management.
    """

    def __init__(self) -> None:
        self._sensors: Dict[str, BaseSensor] = {}

    def register_sensor(self, sensor_id: str, sensor: BaseSensor) -> None:
        self._sensors[sensor_id] = sensor
        logger.info("Registered sensor instance: %s", sensor_id)

    def create_from_config(
        self,
        sensor_type: str,
        sensor_id: str,
        adapter: Any,
        config: Dict[str, Any],
    ) -> BaseSensor:
        """Create and register a sensor from config via SensorFactory."""
        sensor = SensorFactory.create(sensor_type, sensor_id, adapter, config)
        self.register_sensor(sensor_id, sensor)
        return sensor

    def initialize_all(self) -> Dict[str, bool]:
        """Initialize all registered sensors. Returns dict of sensor_id -> success."""
        results: Dict[str, bool] = {}
        for sensor_id, sensor in self._sensors.items():
            try:
                results[sensor_id] = sensor.initialize()
            except Exception as e:
                logger.error("Failed to initialize %s: %s", sensor_id, e)
                results[sensor_id] = False
        return results

    def read_all(self) -> Dict[str, Optional[SensorReading]]:
        """Read from all ready sensors. Returns dict of sensor_id -> reading."""
        readings: Dict[str, Optional[SensorReading]] = {}
        for sensor_id, sensor in self._sensors.items():
            if sensor.get_status() in (SensorStatus.READY, SensorStatus.READING):
                try:
                    readings[sensor_id] = sensor.read()
                except Exception as e:
                    logger.error("Failed to read %s: %s", sensor_id, e)
                    readings[sensor_id] = None
            else:
                readings[sensor_id] = None
        return readings

    def get_sensor(self, sensor_id: str) -> Optional[BaseSensor]:
        return self._sensors.get(sensor_id)

    def get_all_diagnostics(self) -> Dict[str, Dict[str, Any]]:
        return {
            sensor_id: sensor.get_diagnostics()
            for sensor_id, sensor in self._sensors.items()
        }

    def list_sensors(self) -> List[Dict[str, Any]]:
        return [
            {
                "sensor_id": sensor_id,
                "status": sensor.get_status().value,
                "type": type(sensor).__name__,
            }
            for sensor_id, sensor in self._sensors.items()
        ]

    def get_health_summary(self) -> Dict[str, Dict[str, Any]]:
        """Per-sensor health summary for the health API.

        Returns a dict keyed by sensor_id with status, type, and
        error_count extracted from existing diagnostics.
        """
        summary: Dict[str, Dict[str, Any]] = {}
        for sensor_id, sensor in self._sensors.items():
            diag = sensor.get_diagnostics()
            summary[sensor_id] = {
                "status": sensor.get_status().value,
                "type": type(sensor).__name__,
                "error_count": diag.get("error_count", 0),
                "total_reads": diag.get("total_reads", 0),
            }
        return summary

    @property
    def sensor_count(self) -> int:
        return len(self._sensors)
