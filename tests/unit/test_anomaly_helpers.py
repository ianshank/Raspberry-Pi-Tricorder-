"""Tests for mcp_server.anomaly_helpers — extracted pure functions."""

import pytest

from mcp_server.anomaly_helpers import (
    build_anomaly_id,
    coerce_bool,
    coerce_float,
    extract_anomaly_summary,
    severity_from_score,
)


class TestCoerceFloat:
    def test_float_passthrough(self):
        assert coerce_float(1.5) == 1.5

    def test_string_conversion(self):
        assert coerce_float("0.75") == 0.75

    def test_none_returns_none(self):
        assert coerce_float(None) is None

    def test_nan_returns_none(self):
        assert coerce_float(float("nan")) is None

    def test_inf_returns_none(self):
        assert coerce_float(float("inf")) is None

    def test_bad_string_returns_none(self):
        assert coerce_float("bad") is None

    def test_int_converted(self):
        assert coerce_float(3) == 3.0


class TestCoerceBool:
    def test_true_passthrough(self):
        assert coerce_bool(True) is True

    def test_false_passthrough(self):
        assert coerce_bool(False) is False

    @pytest.mark.parametrize("value", ["true", "YES", "1", "on", "y"])
    def test_truthy_strings(self, value):
        assert coerce_bool(value) is True

    @pytest.mark.parametrize("value", ["false", "NO", "0", "off", "n"])
    def test_falsy_strings(self, value):
        assert coerce_bool(value) is False

    def test_int_truthy(self):
        assert coerce_bool(1) is True

    def test_int_falsy(self):
        assert coerce_bool(0) is False

    def test_none_returns_none(self):
        assert coerce_bool(None) is None

    def test_unrecognized_string(self):
        assert coerce_bool("maybe") is None


class TestSeverityFromScore:
    def test_none_score(self):
        assert severity_from_score(None) == "UNKNOWN"

    def test_critical(self):
        assert severity_from_score(0.95) == "CRITICAL"

    def test_high(self):
        assert severity_from_score(0.80) == "HIGH"

    def test_medium(self):
        assert severity_from_score(0.60) == "MEDIUM"

    def test_low(self):
        assert severity_from_score(0.30) == "LOW"

    def test_custom_thresholds(self):
        thresholds = {"critical": 0.95, "high": 0.85, "medium": 0.65}
        assert severity_from_score(0.90, thresholds) == "HIGH"
        assert severity_from_score(0.96, thresholds) == "CRITICAL"

    def test_boundary_critical(self):
        assert severity_from_score(0.9) == "CRITICAL"

    def test_boundary_just_below_critical(self):
        assert severity_from_score(0.899) == "HIGH"

    def test_non_dict_thresholds_uses_default(self):
        assert severity_from_score(0.95, "not a dict") == "CRITICAL"


class TestExtractAnomalySummary:
    def test_from_output(self):
        scan = {"output": {"anomaly_score": 0.85, "is_anomaly": True}}
        result = extract_anomaly_summary(scan, None, fallback_threshold=0.75)
        assert result["anomaly_score"] == 0.85
        assert result["is_anomaly"] is True

    def test_fallback_to_scan_payload(self):
        scan = {"anomaly_score": 0.6}
        result = extract_anomaly_summary(scan, None, fallback_threshold=0.75)
        assert result["anomaly_score"] == 0.6
        assert result["is_anomaly"] is False

    def test_fallback_to_history(self):
        history = {"anomaly_score": 0.9}
        result = extract_anomaly_summary({}, history, fallback_threshold=0.75)
        assert result["anomaly_score"] == 0.9

    def test_custom_severity_thresholds(self):
        scan = {"output": {"anomaly_score": 0.85}}
        thresholds = {"critical": 0.95, "high": 0.80, "medium": 0.60}
        result = extract_anomaly_summary(scan, None, 0.75, severity_thresholds=thresholds)
        assert result["severity"] == "HIGH"

    def test_no_data_defaults(self):
        result = extract_anomaly_summary({}, None, fallback_threshold=0.75)
        assert result["anomaly_score"] is None
        assert result["is_anomaly"] is False
        assert result["severity"] == "UNKNOWN"

    def test_non_dict_scan_result(self):
        result = extract_anomaly_summary("garbage", None, fallback_threshold=0.75)
        assert result["anomaly_score"] is None

    def test_confidence_from_scan(self):
        scan = {"confidence": 0.88}
        result = extract_anomaly_summary(scan, None, fallback_threshold=0.75)
        assert result["confidence"] == 0.88


class TestBuildAnomalyId:
    def test_deterministic(self):
        summary = {"anomaly_score": 0.85, "severity": "HIGH"}
        id1 = build_anomaly_id("model_a", {}, None, summary)
        id2 = build_anomaly_id("model_a", {}, None, summary)
        assert id1 == id2

    def test_prefix(self):
        summary = {"anomaly_score": 0.5, "severity": "MEDIUM"}
        aid = build_anomaly_id("detector", {}, None, summary)
        assert aid.startswith("anom-")

    def test_different_models_different_ids(self):
        summary = {"anomaly_score": 0.5, "severity": "MEDIUM"}
        id1 = build_anomaly_id("model_a", {}, None, summary)
        id2 = build_anomaly_id("model_b", {}, None, summary)
        assert id1 != id2

    def test_uses_history_timestamp(self):
        summary = {"anomaly_score": 0.5, "severity": "MEDIUM"}
        history = {"timestamp": "2026-01-01T00:00:00Z"}
        id_with = build_anomaly_id("m", {}, history, summary)
        id_without = build_anomaly_id("m", {}, None, summary)
        assert id_with != id_without

    def test_uses_scan_timestamp_fallback(self):
        summary = {"anomaly_score": 0.5, "severity": "MEDIUM"}
        scan = {"timestamp": "2026-01-01T00:00:00Z"}
        id_with = build_anomaly_id("m", scan, None, summary)
        id_without = build_anomaly_id("m", {}, None, summary)
        assert id_with != id_without

    def test_uses_output_timestamp_fallback(self):
        summary = {"anomaly_score": 0.5, "severity": "MEDIUM"}
        scan = {"output": {"timestamp": "2026-01-01T00:00:00Z"}}
        id_with = build_anomaly_id("m", scan, None, summary)
        id_without = build_anomaly_id("m", {}, None, summary)
        assert id_with != id_without

    def test_none_score_in_summary(self):
        summary = {"anomaly_score": None, "severity": "UNKNOWN"}
        aid = build_anomaly_id("m", {}, None, summary)
        assert aid.startswith("anom-")
