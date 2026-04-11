"""Tests for sensors.simulation — simulated sensor factories and registry."""


from sensors.base import SensorStatus
from sensors.simulation import (
    _SIMULATION_REGISTRY,
    SimulatedSensor,
    build_simulated_sensor_value,
    register_simulation,
)


class TestSimulationRegistry:
    def test_known_sensor_types_registered(self):
        expected = {"bme680", "mlx90640", "as7265x", "ads1263", "hlk_ld2410", "tfmini", "max30102"}
        assert expected.issubset(set(_SIMULATION_REGISTRY.keys()))

    def test_register_custom_factory(self):
        @register_simulation("test_custom_sensor")
        def _sim_custom(_config):
            return {"test_value": 42}

        assert "test_custom_sensor" in _SIMULATION_REGISTRY
        result = _SIMULATION_REGISTRY["test_custom_sensor"]({})
        assert result == {"test_value": 42}

        # Cleanup
        del _SIMULATION_REGISTRY["test_custom_sensor"]


class TestBuildSimulatedSensorValue:
    def test_bme680_returns_expected_keys(self):
        result = build_simulated_sensor_value("bme680_01", {})
        assert "temperature_c" in result
        assert "humidity_rh" in result
        assert "pressure_hpa" in result
        assert "gas_resistance_ohm" in result

    def test_mlx90640_returns_thermal_frame(self):
        result = build_simulated_sensor_value("mlx90640_01", {})
        assert "thermal_frame" in result
        assert isinstance(result["thermal_frame"], list)
        assert len(result["thermal_frame"]) == 24

    def test_as7265x_returns_spectral_channels(self):
        result = build_simulated_sensor_value("as7265x_01", {})
        assert "spectral_channels" in result
        assert len(result["spectral_channels"]) == 12

    def test_ads1263_with_adc_channels(self):
        config = {"adc_channels": {"gas_mq2": {}, "gas_mq7": {}}}
        result = build_simulated_sensor_value("ads1263_01", config)
        assert "channels" in result
        assert "gas_mq2" in result["channels"]
        assert "gas_mq7" in result["channels"]

    def test_ads1263_without_adc_channels(self):
        result = build_simulated_sensor_value("ads1263_01", {})
        assert "channels" in result
        assert "ch0" in result["channels"]

    def test_hlk_ld2410_returns_presence_data(self):
        result = build_simulated_sensor_value("hlk_ld2410_01", {})
        assert "target_state" in result
        assert "moving_target_distance_cm" in result

    def test_tfmini_s_returns_distance_data(self):
        result = build_simulated_sensor_value("tfmini_s_01", {})
        assert "distance_cm" in result
        assert "valid" in result

    def test_max30102_returns_vitals(self):
        result = build_simulated_sensor_value("max30102_01", {})
        assert "heart_rate_bpm" in result
        assert "spo2_percent" in result

    def test_unknown_sensor_returns_fallback(self):
        result = build_simulated_sensor_value("unknown_sensor_xyz", {})
        assert "value" in result
        assert isinstance(result["value"], float)


class TestSimulatedSensor:
    def test_initialize_returns_true(self):
        sensor = SimulatedSensor("test_bme680", {})
        assert sensor._do_initialize() is True

    def test_read_returns_sensor_reading(self):
        sensor = SimulatedSensor("test_bme680", {})
        sensor.initialize()
        reading = sensor.read()
        assert reading.sensor_id == "test_bme680"
        assert reading.metadata == {"simulated": True}
        assert "temperature_c" in reading.value

    def test_calibrate_returns_true(self):
        sensor = SimulatedSensor("test_bme680", {})
        assert sensor.calibrate() is True
        assert sensor.status == SensorStatus.READY

    def test_diagnostics_includes_simulated_flag(self):
        sensor = SimulatedSensor("test_bme680", {})
        diag = sensor.get_diagnostics()
        assert diag["simulated"] is True

    def test_confidence_uses_constant(self):
        from utils.constants import SIMULATED_SENSOR_CONFIDENCE
        sensor = SimulatedSensor("test_bme680", {})
        sensor.initialize()
        reading = sensor.read()
        assert reading.confidence == SIMULATED_SENSOR_CONFIDENCE
