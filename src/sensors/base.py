"""
Base sensor driver interface with dependency injection and testing support.

All sensor drivers inherit from BaseSensor and implement the abstract methods.
Drivers are hardware-agnostic and use injected I/O adapters for testing.
"""

from abc import ABC
from typing import Any, Dict, Optional, Protocol, runtime_checkable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class SensorStatus(Enum):
    """Sensor operational status."""
    UNINITIALIZED = "uninitialized"
    READY = "ready"
    READING = "reading"
    ERROR = "error"
    CALIBRATING = "calibrating"
    DISABLED = "disabled"


@dataclass
class SensorReading:
    """Standard sensor reading data structure."""
    sensor_id: str
    timestamp: datetime
    value: Any
    unit: Optional[str] = None
    confidence: float = 1.0
    metadata: Optional[Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        val = self.value
        if hasattr(val, 'tolist'):
            val = val.tolist()
        return {
            "sensor_id": self.sensor_id,
            "timestamp": self.timestamp.isoformat(),
            "value": val,
            "unit": self.unit,
            "confidence": self.confidence,
            "metadata": self.metadata or {},
        }


@runtime_checkable
class I2CAdapter(Protocol):
    """Protocol for I2C communication adapter (allows test mocking)."""

    def write_byte(self, address: int, value: int) -> None: ...
    def write_byte_data(self, address: int, register: int, value: int) -> None: ...
    def read_byte_data(self, address: int, register: int) -> int: ...
    def read_i2c_block_data(self, address: int, register: int, length: int) -> list: ...
    def write_i2c_block_data(self, address: int, register: int, data: list) -> None: ...


@runtime_checkable
class SPIAdapter(Protocol):
    """Protocol for SPI communication adapter (allows test mocking)."""

    def open(self, bus: int, device: int) -> None: ...
    def xfer2(self, data: list) -> list: ...
    def close(self) -> None: ...


@runtime_checkable
class UARTAdapter(Protocol):
    """Protocol for UART communication adapter (allows test mocking)."""

    def write(self, data: bytes) -> int: ...
    def read(self, size: int = 1) -> bytes: ...
    def readline(self) -> bytes: ...
    def flush(self) -> None: ...
    @property
    def in_waiting(self) -> int: ...


class BaseSensor(ABC):
    """
    Abstract base class for all sensor drivers.

    Implements dependency injection pattern for I/O adapters.
    """

    def __init__(self, sensor_id: str, adapter: Any, config: Dict[str, Any]):
        self.sensor_id = sensor_id
        self.adapter = adapter
        self.config = config
        self.status = SensorStatus.UNINITIALIZED
        self._last_reading: Optional[SensorReading] = None
        self._error_count = 0
        self._total_reads = 0
        logger.info("Initialized sensor: %s", sensor_id)

    def initialize(self) -> bool:
        """Template method: wraps _do_initialize() with error recording.

        Subclasses should override ``_do_initialize`` (preferred) or this
        method directly for backwards compatibility.
        """
        try:
            result = self._do_initialize()
            self.status = SensorStatus.READY
            return result
        except SensorInitializationError as e:
            self._record_error(e)
            raise
        except Exception as e:
            self._record_error(e)
            raise SensorInitializationError(
                f"Failed to initialize {self.sensor_id}: {e}"
            ) from e

    def read(self) -> SensorReading:
        """Template method: wraps _do_read() with status/recording/error handling.

        Subclasses should override ``_do_read`` (preferred) or this method
        directly for backwards compatibility.
        """
        try:
            self.status = SensorStatus.READING
            reading = self._do_read()
            self._record_reading(reading)
            return reading
        except (SensorCommunicationError, SensorCalibrationError) as e:
            self._record_error(e)
            raise
        except Exception as e:
            self._record_error(e)
            raise SensorCommunicationError(
                f"{self.sensor_id} read failed: {e}"
            ) from e

    def _do_initialize(self) -> bool:
        """Sensor-specific initialization logic.

        Override this method instead of ``initialize()`` to benefit from
        automatic error recording and status management.

        Returns:
            True on success.

        Raises:
            SensorInitializationError: On initialization failure.
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement _do_initialize()"
        )

    def _do_read(self) -> SensorReading:
        """Sensor-specific read logic.

        Override this method instead of ``read()`` to benefit from automatic
        status transitions, reading recording, and error handling.

        Returns:
            A SensorReading with the current sensor data.

        Raises:
            SensorCommunicationError: On read failure.
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement _do_read()"
        )

    def calibrate(self, **kwargs: Any) -> bool:
        """Calibrate sensor (optional)."""
        logger.warning("%s does not implement calibration", self.sensor_id)
        return False

    def reset(self) -> bool:
        """Reset sensor to default state."""
        logger.warning("%s does not implement reset", self.sensor_id)
        return False

    def get_status(self) -> SensorStatus:
        return self.status

    def get_last_reading(self) -> Optional[SensorReading]:
        return self._last_reading

    def get_diagnostics(self) -> Dict[str, Any]:
        error_rate = self._error_count / self._total_reads if self._total_reads > 0 else 0.0
        return {
            "sensor_id": self.sensor_id,
            "status": self.status.value,
            "total_reads": self._total_reads,
            "error_count": self._error_count,
            "error_rate": error_rate,
            "last_reading_time": (
                self._last_reading.timestamp.isoformat() if self._last_reading else None
            ),
        }

    def _record_reading(self, reading: SensorReading) -> None:
        self._last_reading = reading
        self._total_reads += 1
        self.status = SensorStatus.READY

    def _record_error(self, error: Exception) -> None:
        self._error_count += 1
        self._total_reads += 1
        self.status = SensorStatus.ERROR
        logger.error("%s read error: %s", self.sensor_id, error, exc_info=True)


class SensorError(Exception):
    """Base exception for sensor-related errors."""
    pass


class SensorInitializationError(SensorError):
    """Raised when sensor initialization fails."""
    pass


class SensorCommunicationError(SensorError):
    """Raised when sensor communication fails."""
    pass


class SensorCalibrationError(SensorError):
    """Raised when sensor calibration fails."""
    pass


class SensorFactory:
    """Factory for creating sensor instances with injected adapters."""

    _registry: Dict[str, type] = {}

    @classmethod
    def create(cls, sensor_type: str, sensor_id: str, adapter: Any, config: Dict[str, Any]) -> BaseSensor:
        if sensor_type not in cls._registry:
            raise ValueError(
                f"Unknown sensor type: {sensor_type}. Available: {list(cls._registry.keys())}"
            )
        sensor_class = cls._registry[sensor_type]
        return sensor_class(sensor_id, adapter, config)

    @classmethod
    def register(cls, sensor_type: str, sensor_class: type) -> None:
        cls._registry[sensor_type] = sensor_class
        logger.info("Registered sensor type: %s", sensor_type)

    @classmethod
    def list_types(cls) -> list:
        return list(cls._registry.keys())

    @classmethod
    def clear(cls) -> None:
        """Clear registry (for testing)."""
        cls._registry.clear()
