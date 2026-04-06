"""Unit tests for UI configuration models."""

import pytest
from pydantic import ValidationError

from utils.config import PanelConfig, TricorderConfig, UIConfig


class TestPanelConfig:
    def test_valid_panel(self):
        panel = PanelConfig(label="BIO", sensors=["max30102"], color="anakiwa")
        assert panel.label == "BIO"
        assert panel.sensors == ["max30102"]
        assert panel.color == "anakiwa"

    def test_invalid_color(self):
        with pytest.raises(ValueError):
            PanelConfig(label="BIO", sensors=[], color="invalid-color")


class TestUIConfig:
    def test_defaults(self):
        ui = UIConfig()
        assert ui.enabled is True
        assert ui.static_dir == "src/ui/static"
        assert ui.poll_interval_ms == 1000
        assert ui.ws_heartbeat_s == 30
        assert ui.ws_path == "/ws/sensors"
        assert ui.anomaly_ws_path == "/ws/anomalies"
        assert ui.anomaly_poll_interval_ms == 2000
        assert ui.anomaly_model_id == "anomaly_detector"
        assert ui.anomaly_history_limit == 1
        assert ui.anomaly_ack_enabled is True
        assert ui.anomaly_ack_path == "/ui/anomalies/ack"
        assert ui.anomaly_ack_history_limit == 500
        assert ui.anomaly_alert_threshold == pytest.approx(0.75)
        assert ui.agent_enabled is True
        assert ui.agent_chat_path == "/ui/agent/chat"
        assert ui.reconnect_initial_ms == 1500
        assert ui.reconnect_max_ms == 10000
        assert ui.theme == "classic"

    def test_poll_interval_bounds(self):
        with pytest.raises(ValueError):
            UIConfig(poll_interval_ms=99)
        with pytest.raises(ValueError):
            UIConfig(poll_interval_ms=10001)

    def test_anomaly_poll_interval_bounds(self):
        with pytest.raises(ValueError):
            UIConfig(anomaly_poll_interval_ms=249)
        with pytest.raises(ValueError):
            UIConfig(anomaly_poll_interval_ms=60001)

    def test_anomaly_threshold_bounds(self):
        with pytest.raises(ValueError):
            UIConfig(anomaly_alert_threshold=-0.01)
        with pytest.raises(ValueError):
            UIConfig(anomaly_alert_threshold=1.01)

    def test_anomaly_ack_history_limit_bounds(self):
        with pytest.raises(ValueError):
            UIConfig(anomaly_ack_history_limit=0)
        with pytest.raises(ValueError):
            UIConfig(anomaly_ack_history_limit=10001)

    def test_theme_literal_validation(self):
        with pytest.raises(ValueError):
            UIConfig(theme="future")

    def test_ws_path_must_start_with_slash(self):
        with pytest.raises(ValueError):
            UIConfig(ws_path="ws/sensors")
        with pytest.raises(ValueError):
            UIConfig(anomaly_ws_path="ws/anomalies")
        with pytest.raises(ValueError):
            UIConfig(anomaly_ack_path="ui/anomalies/ack")
        with pytest.raises(ValueError):
            UIConfig(agent_chat_path="ui/agent/chat")

    def test_reconnect_bounds_validation(self):
        with pytest.raises(ValueError):
            UIConfig(reconnect_initial_ms=2000, reconnect_max_ms=1000)

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            UIConfig(unexpected_flag=True)

    def test_panel_order_accepted(self):
        ui = UIConfig(panel_order=["bio", "env"])
        assert ui.panel_order == ["bio", "env"]


class TestRootConfigIntegration:
    def test_tricorder_config_has_ui_defaults(self):
        config = TricorderConfig()
        assert config.ui.enabled is True
        assert config.ui.theme == "classic"

    def test_custom_panel_mapping(self):
        config = TricorderConfig(
            ui=UIConfig(
                panels={
                    "env": PanelConfig(
                        label="ENV",
                        sensors=["bme680", "as7265x"],
                        color="golden-tanoi",
                    )
                }
            )
        )
        assert "env" in config.ui.panels
        assert config.ui.panels["env"].sensors == ["bme680", "as7265x"]
