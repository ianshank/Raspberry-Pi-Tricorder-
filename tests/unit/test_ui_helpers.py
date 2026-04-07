"""Tests for mcp_server.ui_helpers — extracted UI pure functions."""

from mcp_server.ui_helpers import (
    build_query_intent_note,
    build_sensor_catalog,
    display_label,
    sanitize_ui_config,
)


class TestDisplayLabel:
    def test_underscores_to_spaces(self):
        assert display_label("bme680_env") == "BME680 ENV"

    def test_hyphens_to_spaces(self):
        assert display_label("hlk-ld2410") == "HLK LD2410"

    def test_already_clean(self):
        assert display_label("sensor") == "SENSOR"

    def test_empty(self):
        assert display_label("") == ""


class TestBuildQueryIntentNote:
    def test_sensor_query_with_data(self):
        snapshot = {"bme680": {}, "mlx90640": {}}
        result = build_query_intent_note("show sensor status", snapshot)
        assert "bme680" in result
        assert "mlx90640" in result

    def test_sensor_query_no_data(self):
        result = build_query_intent_note("sensor diagnostic", {})
        assert "No active sensor streams" in result

    def test_greeting(self):
        result = build_query_intent_note("hello", {})
        assert "Greeting acknowledged" in result

    def test_generic_query(self):
        result = build_query_intent_note("analyze the area", {})
        assert "Query captured" in result

    def test_empty_query(self):
        assert build_query_intent_note("", {}) == ""

    def test_sensor_query_truncation(self):
        snapshot = {f"s{i}": {} for i in range(10)}
        result = build_query_intent_note("sensor status", snapshot)
        assert "..." in result


class TestBuildSensorCatalog:
    def test_i2c_sensors(self):
        config = {
            "sensors": {
                "i2c_devices": {
                    "bme680": {"enabled": True},
                    "mlx90640": {"enabled": True},
                }
            }
        }
        catalog = build_sensor_catalog(config)
        assert "bme680" in catalog
        assert catalog["bme680"]["source"] == "i2c"

    def test_adc_channels(self):
        config = {
            "sensors": {
                "adc_channels": {
                    "ch0": {"label": "Radiation"},
                }
            }
        }
        catalog = build_sensor_catalog(config)
        assert "ads1263:ch0" in catalog
        assert catalog["ads1263:ch0"]["label"] == "Radiation"

    def test_empty_config(self):
        assert build_sensor_catalog({}) == {}

    def test_non_dict_sensors(self):
        assert build_sensor_catalog({"sensors": "broken"}) == {}

    def test_custom_label(self):
        config = {
            "sensors": {
                "i2c_devices": {
                    "bme680": {"label": "Environmental"},
                }
            }
        }
        catalog = build_sensor_catalog(config)
        assert catalog["bme680"]["label"] == "Environmental"


class TestSanitizeUiConfig:
    def test_basic_fields(self):
        result = sanitize_ui_config({}, False, {"project_name": "TEST", "version": "2.0"})
        assert result["project_name"] == "TEST"
        assert result["version"] == "2.0"
        assert result["enabled"] is False

    def test_enabled_requires_static(self):
        result = sanitize_ui_config({"enabled": True}, False, {})
        assert result["enabled"] is False

        result = sanitize_ui_config({"enabled": True}, True, {})
        assert result["enabled"] is True

    def test_panel_order(self):
        ui_config = {
            "panels": {"env": {}, "bio": {}},
            "panel_order": ["bio", "env"],
        }
        result = sanitize_ui_config(ui_config, False, {})
        assert result["panel_order"] == ["bio", "env"]

    def test_default_panel_order(self):
        ui_config = {"panels": {"env": {}, "bio": {}}}
        result = sanitize_ui_config(ui_config, False, {})
        assert set(result["panel_order"]) == {"env", "bio"}

    def test_sensor_catalog_populated(self):
        config = {
            "sensors": {
                "i2c_devices": {"bme680": {"enabled": True}}
            }
        }
        result = sanitize_ui_config({}, False, config)
        assert "bme680" in result["sensor_catalog"]

    def test_unknown_panel_sensor_added_to_catalog(self):
        ui_config = {
            "panels": {"test": {"sensors": ["custom_sensor"]}},
        }
        result = sanitize_ui_config(ui_config, False, {})
        assert "custom_sensor" in result["sensor_catalog"]
        assert result["sensor_catalog"]["custom_sensor"]["source"] == "unknown"
