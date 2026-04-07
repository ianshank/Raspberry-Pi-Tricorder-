"""Tests for shared constants module."""

from utils.constants import (
    AGENT_CHAT_QUERY_MAX_LENGTH,
    DEFAULT_SEVERITY_THRESHOLDS,
    SENSOR_GROUPS,
    SEVERITY_LEVELS,
)


class TestSeverityThresholds:
    """Validate severity threshold constants."""

    def test_keys_present(self):
        assert "critical" in DEFAULT_SEVERITY_THRESHOLDS
        assert "high" in DEFAULT_SEVERITY_THRESHOLDS
        assert "medium" in DEFAULT_SEVERITY_THRESHOLDS

    def test_descending_order(self):
        assert DEFAULT_SEVERITY_THRESHOLDS["critical"] > DEFAULT_SEVERITY_THRESHOLDS["high"]
        assert DEFAULT_SEVERITY_THRESHOLDS["high"] > DEFAULT_SEVERITY_THRESHOLDS["medium"]

    def test_values_in_unit_interval(self):
        for key, value in DEFAULT_SEVERITY_THRESHOLDS.items():
            assert 0.0 < value <= 1.0, f"{key} threshold out of range"

    def test_severity_levels_match_thresholds(self):
        for level in SEVERITY_LEVELS:
            assert level in DEFAULT_SEVERITY_THRESHOLDS


class TestSensorGroups:
    """Validate sensor group constants."""

    def test_expected_groups(self):
        assert "i2c_devices" in SENSOR_GROUPS
        assert "spi_devices" in SENSOR_GROUPS
        assert "uart_devices" in SENSOR_GROUPS

    def test_source_labels(self):
        assert SENSOR_GROUPS["i2c_devices"] == "i2c"
        assert SENSOR_GROUPS["spi_devices"] == "spi"
        assert SENSOR_GROUPS["uart_devices"] == "uart"


class TestQueryLimits:
    """Validate request validation limits."""

    def test_agent_chat_query_max_length(self):
        assert isinstance(AGENT_CHAT_QUERY_MAX_LENGTH, int)
        assert AGENT_CHAT_QUERY_MAX_LENGTH > 0
