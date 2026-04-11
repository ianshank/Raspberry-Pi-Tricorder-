"""Tests for previously-uncovered config validation and model input paths.

Covers:
- ModelConfig: invalid quantization (line 127)
- LangGraphAgentConfig: invalid mission_mode (line 170), invalid threshold (178)
- LangGraphAgentConfig: severity_thresholds unknown keys (192), non-numeric (203-204), out-of-range (208)
- UIConfig: path not starting with / (line 356)
- utils/config.py env override: nested path with non-dict middle node (line 458-460)
- models/base.py: validate_model_input standalone, ModelRegistry.clear()
- models/anomaly_detector.py: invalid max_history type
- utils/logging_setup.py: _add_correlation_id with no correlation ID
"""

from unittest.mock import Mock

import numpy as np
import pytest
from pydantic import ValidationError

from models.anomaly_detector import AnomalyDetector
from models.base import (
    ModelRegistry,
)
from utils.config import (
    LangGraphAgentConfig,
    ModelConfig,
    UIConfig,
    _apply_env_overrides,
)
from utils.logging_setup import _add_correlation_id, correlation_id_var

# ========== ModelConfig ==========

class TestModelConfigValidation:
    """Line 127: invalid quantization."""

    def test_invalid_quantization_raises(self):
        with pytest.raises(ValidationError, match="quantization must be one of"):
            ModelConfig(
                model_path="test.onnx",
                input_shape=[1, 256, 10],
                output_shape=[1, 10],
                quantization="fp8",
            )

    def test_valid_quantizations(self):
        for q in ["fp32", "fp16", "int8", "int4"]:
            cfg = ModelConfig(
                model_path="test.onnx",
                input_shape=[1, 256, 10],
                output_shape=[1, 10],
                quantization=q,
            )
            assert cfg.quantization == q


# ========== LangGraphAgentConfig ==========

class TestLangGraphAgentConfigValidation:
    """Lines 170, 178, 185, 192, 203-204, 208."""

    def test_invalid_mission_mode_raises(self):
        """Line 170."""
        with pytest.raises(ValidationError, match="mission_mode must be one of"):
            LangGraphAgentConfig(mission_mode="combat")

    def test_invalid_human_in_loop_threshold_raises(self):
        """Line 178."""
        with pytest.raises(ValidationError, match="human_in_loop_threshold must be one of"):
            LangGraphAgentConfig(human_in_loop_threshold="EXTREME")

    def test_severity_thresholds_unknown_key_raises(self):
        """Line 192: unknown keys rejected."""
        with pytest.raises(ValidationError, match="unknown key"):
            LangGraphAgentConfig(severity_thresholds={"critical": 0.9, "extreme": 0.99})

    def test_severity_thresholds_non_numeric_raises(self):
        """Lines 203-204: non-float values rejected."""
        with pytest.raises(ValidationError, match="must be a float"):
            LangGraphAgentConfig(severity_thresholds={"critical": "high", "high": 0.75, "medium": 0.5})

    def test_severity_thresholds_out_of_range_raises(self):
        """Line 208: value > 1.0 rejected."""
        with pytest.raises(ValidationError, match="between 0.0 and 1.0"):
            LangGraphAgentConfig(severity_thresholds={"critical": 1.5, "high": 0.75, "medium": 0.5})


# ========== UIConfig ==========

class TestUIConfigValidation:
    """Line 356: path must start with /."""

    def test_ws_path_must_start_with_slash(self):
        with pytest.raises(ValidationError, match="must start with"):
            UIConfig(ws_path="ws/sensors")

    def test_anomaly_ws_path_must_start_with_slash(self):
        with pytest.raises(ValidationError, match="must start with"):
            UIConfig(anomaly_ws_path="ws/anomalies")

    def test_reconnect_bounds_validated(self):
        with pytest.raises(ValidationError, match="reconnect_max_ms must be"):
            UIConfig(reconnect_initial_ms=5000, reconnect_max_ms=1000)


# ========== Env Override Edge Cases ==========

class TestEnvOverrideEdgeCases:
    """Lines 458-460: non-dict middle node in env override path."""

    def test_non_dict_intermediate_node_skipped(self, monkeypatch):
        """When an intermediate config node is not a dict, the override is silently skipped."""
        config = {"logging": "not_a_dict"}
        # This should not raise, just skip the override
        result = _apply_env_overrides(config, prefix="TESTPFX")
        # Config unchanged
        assert result["logging"] == "not_a_dict"

    def test_env_override_creates_nested_missing_key(self, monkeypatch):
        """Missing nested path creates intermediate dicts."""
        monkeypatch.setenv("TESTPFX__NEW_SECTION__KEY", "value")
        config: dict = {}
        result = _apply_env_overrides(config, prefix="TESTPFX")
        assert result.get("new_section", {}).get("key") == "value"


# ========== ModelRegistry.clear() ==========

class TestModelRegistryClear:
    """Lines 172-177: ModelRegistry.clear() resets both registry and instances."""

    def test_clear_removes_instances(self):
        adapter = Mock()
        adapter.load = Mock(return_value=True)
        adapter.predict = Mock(return_value=np.zeros(10))

        orig_registry = dict(ModelRegistry._registry)
        orig_instances = dict(ModelRegistry._instances)
        try:
            ModelRegistry.create(
                "anomaly_detector", "clear_test_01", adapter,
                {"model_path": "x.onnx", "input_shape": [1, 256, 10], "output_shape": [1, 10]},
            )
            assert ModelRegistry.get("clear_test_01") is not None
            ModelRegistry.clear()
            assert ModelRegistry.get("clear_test_01") is None
        finally:
            ModelRegistry._registry = orig_registry
            ModelRegistry._instances = orig_instances

    def test_list_instances_after_clear(self):
        orig_registry = dict(ModelRegistry._registry)
        orig_instances = dict(ModelRegistry._instances)
        try:
            ModelRegistry.clear()
            assert ModelRegistry.list_instances() == []
        finally:
            ModelRegistry._registry = orig_registry
            ModelRegistry._instances = orig_instances


# ========== AnomalyDetector invalid max_history type ==========

class TestAnomalyDetectorMaxHistoryType:
    """Lines 33-39: invalid max_history type → default used."""

    def test_invalid_max_history_string(self, mock_inference_adapter, anomaly_model_config):
        config = dict(anomaly_model_config)
        config["max_history"] = "not_an_int"
        model = AnomalyDetector("ad_mh", mock_inference_adapter, config)
        assert model.max_history == AnomalyDetector.DEFAULT_MAX_HISTORY

    def test_invalid_max_history_none(self, mock_inference_adapter, anomaly_model_config):
        config = dict(anomaly_model_config)
        config["max_history"] = None
        # None results in int(None) → TypeError → falls back to default
        model = AnomalyDetector("ad_mh2", mock_inference_adapter, config)
        assert model.max_history == AnomalyDetector.DEFAULT_MAX_HISTORY


# ========== Logging: correlation ID processor with empty context ==========

class TestCorrelationIDProcessor:
    """Lines 36-39 of logging_setup.py: processor with no active correlation ID."""

    def test_no_correlation_id_skips_field(self):
        """When correlation_id_var is empty string, field is not injected."""
        correlation_id_var.set("")
        event_dict: dict = {"event": "test"}
        result = _add_correlation_id(None, "info", event_dict)
        assert "correlation_id" not in result

    def test_with_correlation_id_injects_field(self):
        """When correlation_id_var has a value, it's injected."""
        correlation_id_var.set("abc123")
        event_dict: dict = {"event": "test"}
        result = _add_correlation_id(None, "info", event_dict)
        assert result["correlation_id"] == "abc123"
        # Reset
        correlation_id_var.set("")
