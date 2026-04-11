"""Simulated sensor factories for development and testing.

Provides a ``_SimulatedSensor`` class and a registry of per-sensor-type
value factories that produce realistic-looking fake data.  Used by the
MCP server when ``environment`` is ``development`` / ``test`` so the full
stack can run without real hardware.

To register a new simulated sensor, add a decorated factory function::

    @register_simulation("my_new_sensor")
    def _sim_my_new_sensor(_sensors_config: Dict[str, Any]) -> Dict[str, Any]:
        return {"value": random.uniform(0, 100)}
"""

import logging
import random
from datetime import datetime, timezone
from typing import Any, Callable, Dict

from sensors.base import BaseSensor, SensorReading, SensorStatus
from utils.constants import SIMULATED_SENSOR_CONFIDENCE

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Simulation registry — each sensor type registers a factory function that
# produces realistic-looking fake data for development / test environments.
# ---------------------------------------------------------------------------
_SIMULATION_REGISTRY: Dict[str, Callable[..., Dict[str, Any]]] = {}


def register_simulation(sensor_pattern: str) -> Callable:
    """Decorator to register a simulated-value factory for *sensor_pattern*."""
    def decorator(func: Callable[..., Dict[str, Any]]) -> Callable[..., Dict[str, Any]]:
        _SIMULATION_REGISTRY[sensor_pattern] = func
        logger.debug("Registered simulation factory: %s", sensor_pattern)
        return func
    return decorator


@register_simulation("bme680")
def _sim_bme680(_sensors_config: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "temperature_c": round(random.uniform(20.0, 26.0), 2),
        "humidity_rh": round(random.uniform(35.0, 60.0), 2),
        "pressure_hpa": round(random.uniform(1005.0, 1022.0), 2),
        "gas_resistance_ohm": round(random.uniform(12000.0, 42000.0), 2),
    }


@register_simulation("mlx90640")
def _sim_mlx90640(_sensors_config: Dict[str, Any]) -> Dict[str, Any]:
    thermal_frame = [round(random.uniform(24.0, 34.0), 2) for _ in range(24)]
    return {
        "min_temp_c": min(thermal_frame),
        "avg_temp_c": round(sum(thermal_frame) / len(thermal_frame), 2),
        "max_temp_c": max(thermal_frame),
        "thermal_frame": thermal_frame,
    }


@register_simulation("as7265x")
def _sim_as7265x(_sensors_config: Dict[str, Any]) -> Dict[str, Any]:
    wavelengths = (
        "410nm", "435nm", "460nm", "485nm", "510nm", "535nm",
        "560nm", "585nm", "610nm", "645nm", "680nm", "705nm",
    )
    return {
        "spectral_channels": {
            name: round(random.uniform(0.05, 1.0), 3) for name in wavelengths
        }
    }


@register_simulation("ads1263")
def _sim_ads1263(sensors_config: Dict[str, Any]) -> Dict[str, Any]:
    adc_channels = sensors_config.get("adc_channels", {})
    if isinstance(adc_channels, dict) and adc_channels:
        channel_values = {
            str(channel_id): round(random.uniform(0.02, 2.8), 3)
            for channel_id in adc_channels.keys()
        }
    else:
        channel_values = {
            "ch0": round(random.uniform(0.02, 2.8), 3),
            "ch1": round(random.uniform(0.02, 2.8), 3),
        }
    return {"channels": channel_values}


@register_simulation("hlk_ld2410")
def _sim_hlk_ld2410(_sensors_config: Dict[str, Any]) -> Dict[str, Any]:
    moving_distance = random.randint(50, 450)
    still_distance = random.randint(30, 220)
    detection_distance = max(moving_distance, still_distance)
    return {
        "target_state": random.choice(["moving", "still", "none"]),
        "moving_target_energy": random.randint(0, 100),
        "stationary_target_energy": random.randint(0, 100),
        "moving_target_distance_cm": moving_distance,
        "stationary_target_distance_cm": still_distance,
        "detection_distance_cm": detection_distance,
    }


@register_simulation("tfmini")
def _sim_tfmini(_sensors_config: Dict[str, Any]) -> Dict[str, Any]:
    valid = random.random() > 0.1
    return {
        "distance_cm": random.randint(35, 500) if valid else None,
        "signal_strength": random.randint(30, 200) if valid else None,
        "temperature_c": round(random.uniform(25.0, 37.0), 2) if valid else None,
        "max_range_cm": 1200,
        "valid": valid,
    }


@register_simulation("max30102")
def _sim_max30102(_sensors_config: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "heart_rate_bpm": round(random.uniform(58.0, 92.0), 1),
        "spo2_percent": round(random.uniform(95.0, 100.0), 1),
        "ir_avg": round(random.uniform(32000.0, 76000.0), 2),
    }


def build_simulated_sensor_value(sensor_id: str, sensors_config: Dict[str, Any]) -> Dict[str, Any]:
    """Return simulated sensor data for *sensor_id*.

    Looks up the sensor type from the registry using substring matching.
    Falls back to a random scalar value if no factory is registered.
    """
    sensor_key = sensor_id.lower()
    for pattern, factory in _SIMULATION_REGISTRY.items():
        if pattern in sensor_key:
            return factory(sensors_config)
    return {"value": round(random.uniform(0.0, 1.0), 4)}


class SimulatedSensor(BaseSensor):
    """Development-only simulated sensor used when hardware is unavailable."""

    def __init__(self, sensor_id: str, sensors_config: Dict[str, Any]) -> None:
        super().__init__(sensor_id=sensor_id, adapter=None, config={"simulated": True})
        self._sensors_config = sensors_config

    def _do_initialize(self) -> bool:
        return True

    def _do_read(self) -> SensorReading:
        return SensorReading(
            sensor_id=self.sensor_id,
            timestamp=datetime.now(timezone.utc),
            value=build_simulated_sensor_value(self.sensor_id, self._sensors_config),
            confidence=SIMULATED_SENSOR_CONFIDENCE,
            metadata={"simulated": True},
        )

    def calibrate(self, **kwargs: Any) -> bool:
        self.status = SensorStatus.CALIBRATING
        self.status = SensorStatus.READY
        return True

    def get_diagnostics(self) -> Dict[str, Any]:
        diagnostics = super().get_diagnostics()
        diagnostics["simulated"] = True
        return diagnostics
