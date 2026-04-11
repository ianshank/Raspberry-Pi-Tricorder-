"""Unit tests for sensor base framework."""

from datetime import datetime, timezone
from unittest.mock import Mock

import numpy as np
import pytest

from sensors.base import (
    BaseSensor,
    SensorCalibrationError,
    SensorCommunicationError,
    SensorError,
    SensorFactory,
    SensorInitializationError,
    SensorReading,
    SensorStatus,
)


class TestSensorReading:
    def test_to_dict_basic(self, sample_sensor_reading):
        result = sample_sensor_reading.to_dict()
        assert result["sensor_id"] == "test_sensor_001"
        assert result["unit"] == "composite"
        assert result["confidence"] == 0.95
        assert "timestamp" in result
        assert "value" in result

    def test_to_dict_with_numpy(self):
        reading = SensorReading(
            sensor_id="array_sensor",
            timestamp=datetime.now(timezone.utc),
            value=np.array([[1, 2], [3, 4]]),
            unit="pixels",
        )
        result = reading.to_dict()
        assert result["value"] == [[1, 2], [3, 4]]

    def test_to_dict_scalar(self):
        reading = SensorReading(
            sensor_id="simple",
            timestamp=datetime.now(timezone.utc),
            value=42.0,
        )
        result = reading.to_dict()
        assert result["value"] == 42.0

    def test_default_metadata(self):
        reading = SensorReading(
            sensor_id="test",
            timestamp=datetime.now(timezone.utc),
            value=0,
        )
        assert reading.metadata == {}

    def test_default_confidence(self):
        reading = SensorReading(
            sensor_id="test",
            timestamp=datetime.now(timezone.utc),
            value=0,
        )
        assert reading.confidence == 1.0


class TestSensorStatus:
    def test_all_statuses(self):
        assert SensorStatus.UNINITIALIZED.value == "uninitialized"
        assert SensorStatus.READY.value == "ready"
        assert SensorStatus.READING.value == "reading"
        assert SensorStatus.ERROR.value == "error"
        assert SensorStatus.CALIBRATING.value == "calibrating"
        assert SensorStatus.DISABLED.value == "disabled"


class TestBaseSensorAbstract:
    def test_unimplemented_do_methods_raise(self):
        """BaseSensor can be instantiated but _do_initialize/_do_read raise via template."""
        from sensors.base import SensorCommunicationError, SensorInitializationError
        sensor = BaseSensor("test", Mock(), {})
        with pytest.raises(SensorInitializationError):
            sensor.initialize()
        with pytest.raises(SensorCommunicationError):
            sensor.read()

    def test_concrete_subclass(self):
        class ConcreteSensor(BaseSensor):
            def initialize(self): return True
            def read(self):
                return SensorReading("concrete", datetime.now(timezone.utc), 42)

        sensor = ConcreteSensor("s1", Mock(), {})
        assert sensor.sensor_id == "s1"
        assert sensor.status == SensorStatus.UNINITIALIZED
        assert sensor._error_count == 0
        assert sensor._total_reads == 0

    def test_calibrate_default(self):
        class ConcreteSensor(BaseSensor):
            def initialize(self): return True
            def read(self):
                return SensorReading("concrete", datetime.now(timezone.utc), 42)

        sensor = ConcreteSensor("s1", Mock(), {})
        assert sensor.calibrate() is False

    def test_reset_default(self):
        class ConcreteSensor(BaseSensor):
            def initialize(self): return True
            def read(self):
                return SensorReading("concrete", datetime.now(timezone.utc), 42)

        sensor = ConcreteSensor("s1", Mock(), {})
        assert sensor.reset() is False

    def test_get_last_reading_none(self):
        class ConcreteSensor(BaseSensor):
            def initialize(self): return True
            def read(self):
                return SensorReading("concrete", datetime.now(timezone.utc), 42)

        sensor = ConcreteSensor("s1", Mock(), {})
        assert sensor.get_last_reading() is None

    def test_record_reading(self):
        class ConcreteSensor(BaseSensor):
            def initialize(self): return True
            def read(self):
                reading = SensorReading("s1", datetime.now(timezone.utc), 42)
                self._record_reading(reading)
                return reading

        sensor = ConcreteSensor("s1", Mock(), {})
        reading = sensor.read()
        assert sensor.get_last_reading() == reading
        assert sensor._total_reads == 1
        assert sensor.status == SensorStatus.READY

    def test_record_error(self):
        class ConcreteSensor(BaseSensor):
            def initialize(self): return True
            def read(self):
                error = RuntimeError("test")
                self._record_error(error)
                raise error

        sensor = ConcreteSensor("s1", Mock(), {})
        with pytest.raises(RuntimeError):
            sensor.read()
        assert sensor._error_count == 1
        assert sensor.status == SensorStatus.ERROR

    def test_diagnostics(self):
        class ConcreteSensor(BaseSensor):
            def initialize(self): return True
            def read(self):
                reading = SensorReading("s1", datetime.now(timezone.utc), 42)
                self._record_reading(reading)
                return reading

        sensor = ConcreteSensor("s1", Mock(), {})
        sensor.read()
        diag = sensor.get_diagnostics()
        assert diag["sensor_id"] == "s1"
        assert diag["total_reads"] == 1
        assert diag["error_count"] == 0
        assert diag["error_rate"] == 0.0
        assert diag["last_reading_time"] is not None

    def test_diagnostics_no_reads(self):
        class ConcreteSensor(BaseSensor):
            def initialize(self): return True
            def read(self):
                return SensorReading("s1", datetime.now(timezone.utc), 42)

        sensor = ConcreteSensor("s1", Mock(), {})
        diag = sensor.get_diagnostics()
        assert diag["error_rate"] == 0.0
        assert diag["last_reading_time"] is None


class TestSensorFactory:
    def setup_method(self):
        """Save and restore registry state."""
        self._original_registry = SensorFactory._registry.copy()

    def teardown_method(self):
        SensorFactory._registry = self._original_registry

    def test_create_registered_type(self):
        class TestSensor(BaseSensor):
            def initialize(self): return True
            def read(self): return SensorReading("t", datetime.now(timezone.utc), 0)

        SensorFactory.register("test_type", TestSensor)
        sensor = SensorFactory.create("test_type", "t1", Mock(), {})
        assert isinstance(sensor, TestSensor)

    def test_create_unknown_type(self):
        with pytest.raises(ValueError, match="Unknown sensor type"):
            SensorFactory.create("nonexistent", "t1", Mock(), {})

    def test_list_types(self):
        types = SensorFactory.list_types()
        assert isinstance(types, list)

    def test_register_and_create(self):
        class CustomSensor(BaseSensor):
            def initialize(self): return True
            def read(self): return SensorReading("c", datetime.now(timezone.utc), 0)

        SensorFactory.register("custom_test", CustomSensor)
        assert "custom_test" in SensorFactory.list_types()
        sensor = SensorFactory.create("custom_test", "c1", Mock(), {})
        assert sensor.sensor_id == "c1"


class TestSensorExceptions:
    def test_hierarchy(self):
        assert issubclass(SensorInitializationError, SensorError)
        assert issubclass(SensorCommunicationError, SensorError)
        assert issubclass(SensorCalibrationError, SensorError)

    def test_raise_and_catch(self):
        with pytest.raises(SensorError):
            raise SensorInitializationError("test")

    def test_message(self):
        err = SensorCommunicationError("I2C bus error")
        assert "I2C bus error" in str(err)
