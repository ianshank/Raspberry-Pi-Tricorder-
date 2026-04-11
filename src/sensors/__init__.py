"""Sensor drivers package. Importing this module registers all sensor types."""

import sensors.ads1263  # noqa: F401
import sensors.as7265x  # noqa: F401

# Import drivers to trigger SensorFactory.register() calls
import sensors.bme680  # noqa: F401
import sensors.hlk_ld2410  # noqa: F401
import sensors.max30102  # noqa: F401
import sensors.mlx90640  # noqa: F401
import sensors.tfmini_s  # noqa: F401
from sensors.base import (
    BaseSensor,
    I2CAdapter,
    SensorCalibrationError,
    SensorCommunicationError,
    SensorError,
    SensorFactory,
    SensorInitializationError,
    SensorReading,
    SensorStatus,
    SPIAdapter,
    UARTAdapter,
)
from sensors.manager import SensorManager
from sensors.simulation import SimulatedSensor

__all__ = [
    "BaseSensor",
    "SensorReading",
    "SensorStatus",
    "SensorError",
    "SensorInitializationError",
    "SensorCommunicationError",
    "SensorCalibrationError",
    "SensorFactory",
    "SensorManager",
    "SimulatedSensor",
    "I2CAdapter",
    "SPIAdapter",
    "UARTAdapter",
]
