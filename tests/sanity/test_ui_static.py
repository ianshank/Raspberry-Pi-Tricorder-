"""Sanity checks for static UI assets and module wiring."""

from pathlib import Path


def _static_root() -> Path:
    return Path(__file__).resolve().parents[2] / "src" / "ui" / "static"


class TestUIStaticAssets:
    def test_expected_files_exist(self):
        root = _static_root()
        expected = [
            root / "index.html",
            root / "css" / "tricorder.css",
            root / "js" / "app.js",
            root / "js" / "services" / "data-service.js",
            root / "js" / "components" / "base-panel.js",
            root / "js" / "components" / "bio-panel.js",
            root / "js" / "components" / "env-panel.js",
            root / "js" / "components" / "eng-panel.js",
            root / "js" / "components" / "agent-chat-panel.js",
            root / "js" / "components" / "anomaly-alert-stack.js",
            root / "js" / "components" / "panel-factory.js",
            root / "js" / "components" / "render-utils.js",
            root / "vendor" / "lcars" / "lcars.css",
        ]
        for path in expected:
            assert path.exists(), f"Missing UI asset: {path}"

    def test_index_references_vendor_and_module_entrypoint(self):
        html = (_static_root() / "index.html").read_text(encoding="utf-8")
        assert "./vendor/lcars/lcars.css" in html
        assert "./css/tricorder.css" in html
        assert "./js/app.js" in html
        assert "id=\"alert-stack\"" in html
        assert "id=\"panel-host\"" in html

    def test_app_uses_modular_services_and_components(self):
        app_js = (_static_root() / "js" / "app.js").read_text(encoding="utf-8")
        assert "./services/data-service.js" in app_js
        assert "./components/panel-factory.js" in app_js
        assert "./components/anomaly-alert-stack.js" in app_js
        assert "fetchUiConfig" in app_js
        assert "orderedPanelKeys" in app_js

    def test_panel_factory_supports_agent_panel(self):
        panel_factory_js = (
            _static_root() / "js" / "components" / "panel-factory.js"
        ).read_text(encoding="utf-8")
        assert "./agent-chat-panel.js" in panel_factory_js
        assert "key.includes(\"agent\")" in panel_factory_js

    def test_data_service_supports_anomaly_stream(self):
        data_service_js = (
            _static_root() / "js" / "services" / "data-service.js"
        ).read_text(encoding="utf-8")
        assert "connectAnomalies" in data_service_js
        assert "subscribeAnomalies" in data_service_js
        assert "anomaly_ws_path" in data_service_js

    def test_anomaly_alert_stack_supports_acknowledgment(self):
        alert_stack_js = (
            _static_root() / "js" / "components" / "anomaly-alert-stack.js"
        ).read_text(encoding="utf-8")
        assert "anomaly_ack_path" in alert_stack_js
        assert "anomaly_id" in alert_stack_js
        assert "ACKNOWLEDGED" in alert_stack_js

    def test_agent_chat_panel_uses_configured_chat_path(self):
        panel_js = (
            _static_root() / "js" / "components" / "agent-chat-panel.js"
        ).read_text(encoding="utf-8")
        assert "agent_chat_path" in panel_js
        assert "include_sensor_context" in panel_js
