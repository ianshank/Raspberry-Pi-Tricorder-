"""Tests for new production-grade features: structured logging, feature flags,
exception hierarchies, input validation, and configurable limits."""

import logging
from unittest.mock import Mock

import numpy as np
import pytest

from utils.config import (
    FeatureFlagsConfig,
    LoggingConfig,
    TricorderConfig,
    load_config,
)
from utils.logging_setup import (
    set_correlation_id,
    correlation_id_var,
    setup_logging,
)
from models.base import (
    ModelInferenceError,
    validate_model_input,
)
from models.anomaly_detector import AnomalyDetector
from models.fusion_engine import FusionEngine
from agents.langgraph_agent import AgentError, AgentToolError, AgentTimeoutError
from mcp_server.server import MCPServerError, ToolExecutionError, AuthenticationError


# ========== Structured Logging ==========


class TestStructuredLogging:
    """Validate structlog integration and correlation ID injection."""

    def test_setup_console_only_default(self):
        """Default (non-JSON) logging still configures without errors."""
        config = LoggingConfig(level="DEBUG", file_path=None, json_format=False)
        setup_logging(config)
        root = logging.getLogger()
        assert root.level == logging.DEBUG
        assert len(root.handlers) >= 1

    def test_setup_json_mode(self):
        """JSON mode produces a handler with structlog ProcessorFormatter."""
        config = LoggingConfig(level="INFO", file_path=None, json_format=True)
        setup_logging(config)
        root = logging.getLogger()
        assert root.level == logging.INFO
        assert len(root.handlers) >= 1

    def test_setup_with_file_and_json(self, tmp_path):
        """File + JSON mode coexist without error."""
        log_file = tmp_path / "test.log"
        config = LoggingConfig(
            level="WARNING",
            file_path=str(log_file),
            max_bytes=1024,
            backup_count=1,
            json_format=True,
        )
        setup_logging(config)
        root = logging.getLogger()
        assert root.level == logging.WARNING
        assert len(root.handlers) >= 2  # console + file

    def test_correlation_id_set_and_get(self):
        """set_correlation_id stores and returns a value."""
        cid = set_correlation_id("test-123")
        assert cid == "test-123"
        assert correlation_id_var.get() == "test-123"

    def test_correlation_id_auto_generate(self):
        """Omitting the argument auto-generates a 16-char hex ID."""
        cid = set_correlation_id()
        assert len(cid) == 16
        int(cid, 16)  # must be valid hex

    def test_handler_dedup_on_reinit(self):
        """Re-calling setup_logging should not duplicate handlers."""
        config = LoggingConfig(level="INFO", file_path=None, json_format=False)
        setup_logging(config)
        count1 = len(logging.getLogger().handlers)
        setup_logging(config)
        count2 = len(logging.getLogger().handlers)
        assert count2 == count1


# ========== Feature Flags ==========


class TestFeatureFlags:
    """Validate FeatureFlagsConfig defaults and overrides."""

    def test_defaults(self):
        flags = FeatureFlagsConfig()
        assert flags.structured_logging is False
        assert flags.anomaly_ack is True
        assert flags.agent_chat is True
        assert flags.mqtt_publishing is True

    def test_override(self):
        flags = FeatureFlagsConfig(structured_logging=True, mqtt_publishing=False)
        assert flags.structured_logging is True
        assert flags.mqtt_publishing is False

    def test_root_config_includes_flags(self):
        """TricorderConfig includes feature_flags with defaults."""
        cfg = TricorderConfig()
        assert hasattr(cfg, "feature_flags")
        assert cfg.feature_flags.anomaly_ack is True

    def test_load_config_with_flags(self, tmp_path):
        """YAML with feature_flags section parses correctly."""
        yaml_content = """
environment: "development"
feature_flags:
  structured_logging: true
  mqtt_publishing: false
"""
        config_file = tmp_path / "test.yaml"
        config_file.write_text(yaml_content)
        cfg = load_config(config_file)
        assert cfg.feature_flags.structured_logging is True
        assert cfg.feature_flags.mqtt_publishing is False
        # Defaults preserved for unspecified flags
        assert cfg.feature_flags.anomaly_ack is True

    def test_logging_json_format_field(self):
        """LoggingConfig.json_format defaults to False."""
        cfg = LoggingConfig()
        assert cfg.json_format is False

    def test_logging_json_format_override(self):
        cfg = LoggingConfig(json_format=True)
        assert cfg.json_format is True


# ========== Exception Hierarchies ==========


class TestAgentExceptions:
    """Agent exception hierarchy."""

    def test_agent_error_base(self):
        assert issubclass(AgentToolError, AgentError)
        assert issubclass(AgentTimeoutError, AgentError)

    def test_agent_error_message(self):
        err = AgentToolError("read_sensor failed")
        assert "read_sensor failed" in str(err)


class TestMCPServerExceptions:
    """MCP server exception hierarchy."""

    def test_mcp_server_error_base(self):
        assert issubclass(ToolExecutionError, MCPServerError)
        assert issubclass(AuthenticationError, MCPServerError)

    def test_tool_execution_error_message(self):
        err = ToolExecutionError("Tool timed out")
        assert "Tool timed out" in str(err)


# ========== Model Input Validation ==========


class TestValidateModelInput:
    """validate_model_input rejects NaN and Inf."""

    def test_clean_input_passthrough(self):
        data = np.array([1.0, 2.0, 3.0])
        result = validate_model_input(data)
        assert np.array_equal(result, data)

    def test_nan_rejected(self):
        data = np.array([1.0, float("nan"), 3.0])
        with pytest.raises(ModelInferenceError, match="NaN or infinite"):
            validate_model_input(data)

    def test_inf_rejected(self):
        data = np.array([1.0, float("inf"), 3.0])
        with pytest.raises(ModelInferenceError, match="NaN or infinite"):
            validate_model_input(data)

    def test_neg_inf_rejected(self):
        data = np.array([1.0, float("-inf"), 3.0])
        with pytest.raises(ModelInferenceError, match="NaN or infinite"):
            validate_model_input(data)

    def test_custom_name_in_error(self):
        data = np.array([float("nan")])
        with pytest.raises(ModelInferenceError, match="my_sensor"):
            validate_model_input(data, name="my_sensor")

    def test_multidim_nan_detected(self):
        data = np.ones((2, 3, 4))
        data[1, 2, 3] = float("nan")
        with pytest.raises(ModelInferenceError):
            validate_model_input(data)


class TestAnomalyDetectorNaNValidation:
    """NaN/inf inputs are rejected before inference runs."""

    def test_nan_input_rejected(self, mock_inference_adapter, anomaly_model_config):
        model = AnomalyDetector("ad_nan", mock_inference_adapter, anomaly_model_config)
        model.load()
        bad = np.ones((1, 256, 10), dtype=np.float32)
        bad[0, 0, 0] = float("nan")
        with pytest.raises(ModelInferenceError, match="NaN or infinite"):
            model.predict(bad)

    def test_inf_input_rejected(self, mock_inference_adapter, anomaly_model_config):
        model = AnomalyDetector("ad_inf", mock_inference_adapter, anomaly_model_config)
        model.load()
        bad = np.ones((1, 256, 10), dtype=np.float32)
        bad[0, 0, 0] = float("inf")
        with pytest.raises(ModelInferenceError, match="NaN or infinite"):
            model.predict(bad)


class TestFusionEngineNaNValidation:
    """NaN/inf inputs are rejected before fusion inference."""

    def test_nan_input_rejected(self, mock_inference_adapter, fusion_model_config):
        model = FusionEngine("fe_nan", mock_inference_adapter, fusion_model_config)
        model.load()
        bad = np.ones((1, 16, 64), dtype=np.float32)
        bad[0, 0, 0] = float("nan")
        with pytest.raises(ModelInferenceError, match="NaN or infinite"):
            model.predict(bad)


# ========== Configurable MAX_SENSOR_DATA_ITEMS ==========


class TestConfigurableAnomalyLimit:
    """register_anomaly_tools accepts configurable max_sensor_data_items."""

    def test_default_limit(self):
        from mcp_server.tools.anomaly_tools import DEFAULT_MAX_SENSOR_DATA_ITEMS
        assert DEFAULT_MAX_SENSOR_DATA_ITEMS == 10_000

    def test_custom_limit_applied(self):
        from mcp_server.tools.anomaly_tools import register_anomaly_tools
        from mcp_server.server import ToolRegistry
        from models.base import ModelRegistry

        mock_model = Mock()
        mock_model.input_shape = [1, 256, 10]
        mock_model.predict = Mock(return_value=Mock(to_dict=Mock(return_value={"score": 0.5})))

        orig_get = ModelRegistry.get
        ModelRegistry.get = Mock(return_value=mock_model)
        try:
            registry = ToolRegistry()
            # Use a very small limit
            register_anomaly_tools(registry, max_sensor_data_items=5)
            assert registry.has_tool("run_anomaly_scan")

            # Call with data exceeding the custom limit
            func = registry._tools["run_anomaly_scan"]
            result = func(sensor_data=list(range(10)))
            assert "error" in result
            assert "5" in result["error"]
        finally:
            ModelRegistry.get = orig_get
