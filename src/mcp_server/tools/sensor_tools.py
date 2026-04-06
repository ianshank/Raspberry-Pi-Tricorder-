"""MCP tools for sensor operations."""

from typing import Any, Dict, Optional
import logging

from sensors.manager import SensorManager

logger = logging.getLogger(__name__)

GENERIC_SENSOR_READ_ERROR = "Sensor read operation failed. Check logs for details."
GENERIC_SENSOR_CALIBRATION_ERROR = "Sensor calibration failed. Check logs for details."


def register_sensor_tools(registry, sensor_manager: SensorManager) -> None:
    """
    Register all sensor-related MCP tools with the given registry.

    Dynamically creates tools based on the sensor manager's state.
    """

    def read_sensor(sensor_id: str) -> Dict[str, Any]:
        """Read current value from a specific sensor."""
        sensor = sensor_manager.get_sensor(sensor_id)
        if sensor is None:
            return {"error": f"Sensor not found: {sensor_id}"}
        try:
            reading = sensor.read()
            return reading.to_dict()
        except Exception as e:
            logger.error("read_sensor(%s) failed: %s", sensor_id, e, exc_info=True)
            return {"error": GENERIC_SENSOR_READ_ERROR}

    registry.register_function(
        name="read_sensor",
        description="Read current value from a specific sensor by ID",
        input_schema={
            "type": "object",
            "properties": {
                "sensor_id": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 128,
                    "description": "Unique sensor identifier",
                }
            },
            "required": ["sensor_id"],
        },
        func=read_sensor,
    )

    def list_sensors() -> list:
        """List all available sensors and their status."""
        return sensor_manager.list_sensors()

    registry.register_function(
        name="list_sensors",
        description="List all available sensors and their current status",
        input_schema={"type": "object", "properties": {}},
        func=list_sensors,
    )

    def read_all_sensors() -> Dict[str, Any]:
        """Read from all ready sensors."""
        readings = sensor_manager.read_all()
        result = {}
        for sensor_id, reading in readings.items():
            result[sensor_id] = reading.to_dict() if reading else None
        return result

    registry.register_function(
        name="read_all_sensors",
        description="Read current values from all ready sensors",
        input_schema={"type": "object", "properties": {}},
        func=read_all_sensors,
    )

    def get_sensor_diagnostics(sensor_id: Optional[str] = None) -> Dict[str, Any]:
        """Get diagnostic information for sensor(s)."""
        if sensor_id:
            sensor = sensor_manager.get_sensor(sensor_id)
            if sensor is None:
                return {"error": f"Sensor not found: {sensor_id}"}
            return sensor.get_diagnostics()
        return sensor_manager.get_all_diagnostics()

    registry.register_function(
        name="get_sensor_diagnostics",
        description="Get diagnostic info for a specific sensor or all sensors",
        input_schema={
            "type": "object",
            "properties": {
                "sensor_id": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 128,
                    "description": "Optional sensor ID. If omitted, returns all diagnostics.",
                }
            },
        },
        func=get_sensor_diagnostics,
    )

    def calibrate_sensor(sensor_id: str) -> Dict[str, Any]:
        """Trigger calibration for a sensor."""
        sensor = sensor_manager.get_sensor(sensor_id)
        if sensor is None:
            return {"error": f"Sensor not found: {sensor_id}"}
        try:
            success = sensor.calibrate()
            return {"sensor_id": sensor_id, "calibration_success": success}
        except Exception as e:
            logger.error("calibrate_sensor(%s) failed: %s", sensor_id, e, exc_info=True)
            return {"error": GENERIC_SENSOR_CALIBRATION_ERROR}

    registry.register_function(
        name="calibrate_sensor",
        description="Trigger calibration for a specific sensor",
        input_schema={
            "type": "object",
            "properties": {
                "sensor_id": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 128,
                    "description": "Sensor to calibrate",
                }
            },
            "required": ["sensor_id"],
        },
        func=calibrate_sensor,
    )
