"""Tests for ConfigManager hot-reload functionality."""

import threading
from unittest.mock import MagicMock

import pytest

from utils.config import ConfigManager, TricorderConfig


@pytest.fixture
def base_config():
    """Minimal valid TricorderConfig for testing."""
    return TricorderConfig(
        admin={"enabled": True, "hmac_secret": "test-secret", "allowed_sections": ["ui", "logging", "feature_flags"]},
    )


@pytest.fixture
def manager(base_config):
    return ConfigManager(base_config)


class TestConfigManagerBasics:
    def test_config_property(self, manager, base_config):
        assert manager.config.version == base_config.version

    def test_get_sanitized_redacts_api_key(self):
        config = TricorderConfig(mcp_server={"host": "0.0.0.0", "api_key": "secret123"})
        mgr = ConfigManager(config)
        sanitized = mgr.get_sanitized()
        assert sanitized["mcp_server"]["api_key"] == "***"

    def test_get_sanitized_redacts_hmac_secret(self):
        config = TricorderConfig(admin={"hmac_secret": "secret123"})
        mgr = ConfigManager(config)
        sanitized = mgr.get_sanitized()
        assert sanitized["admin"]["hmac_secret"] == "***"

    def test_get_sanitized_no_secrets(self, manager):
        sanitized = manager.get_sanitized()
        assert "version" in sanitized


class TestConfigManagerReload:
    def test_reload_logging_level(self, manager):
        diff = manager.reload({"logging": {"level": "DEBUG"}})
        assert "logging" in diff
        assert diff["logging"]["new"]["level"] == "DEBUG"
        assert manager.config.logging.level == "DEBUG"

    def test_reload_feature_flags(self, manager):
        diff = manager.reload({"feature_flags": {"llm_enabled": True}})
        assert "feature_flags" in diff
        assert manager.config.feature_flags.llm_enabled is True

    def test_reload_ui_config(self, manager):
        diff = manager.reload({"ui": {"debug": True}})
        assert "ui" in diff
        assert manager.config.ui.debug is True

    @pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
    def test_reload_all_valid_log_levels(self, base_config, level):
        """All valid log levels can be applied via reload."""
        mgr = ConfigManager(base_config)
        mgr.reload({"logging": {"level": level}})
        assert mgr.config.logging.level == level

    def test_reload_no_change_returns_empty_diff(self, manager):
        current_level = manager.config.logging.level
        diff = manager.reload({"logging": {"level": current_level}})
        assert diff == {}

    def test_reload_rejects_disallowed_section(self, manager):
        with pytest.raises(ValueError, match="not allowed"):
            manager.reload({"sensors": {"i2c_devices": {}}})

    def test_reload_rejects_non_dict_section(self, manager):
        with pytest.raises(ValueError, match="must be a dict"):
            manager.reload({"logging": "not-a-dict"})

    def test_reload_rejects_invalid_value(self, manager):
        with pytest.raises(Exception):  # Pydantic ValidationError
            manager.reload({"logging": {"level": "INVALID_LEVEL"}})

    def test_reload_custom_allowed_sections(self, manager):
        manager.reload(
            {"logging": {"level": "WARNING"}},
            allowed_sections=["logging"],
        )
        assert manager.config.logging.level == "WARNING"

    def test_reload_custom_allowed_rejects_others(self, manager):
        with pytest.raises(ValueError, match="not allowed"):
            manager.reload(
                {"feature_flags": {"llm_enabled": True}},
                allowed_sections=["logging"],
            )


class TestConfigManagerObservers:
    def test_observer_called_on_change(self, manager):
        observer = MagicMock()
        manager.add_observer(observer)

        manager.reload({"logging": {"level": "DEBUG"}})

        observer.assert_called_once()
        args = observer.call_args[0]
        assert args[0] == "logging"  # section
        assert args[1]["level"] == "INFO"  # old
        assert args[2]["level"] == "DEBUG"  # new

    def test_observer_not_called_when_no_change(self, manager):
        observer = MagicMock()
        manager.add_observer(observer)

        current_level = manager.config.logging.level
        manager.reload({"logging": {"level": current_level}})

        observer.assert_not_called()

    def test_multiple_observers(self, manager):
        obs1 = MagicMock()
        obs2 = MagicMock()
        manager.add_observer(obs1)
        manager.add_observer(obs2)

        manager.reload({"logging": {"level": "DEBUG"}})

        obs1.assert_called_once()
        obs2.assert_called_once()

    def test_observer_exception_does_not_break_reload(self, manager):
        bad_observer = MagicMock(side_effect=RuntimeError("observer error"))
        good_observer = MagicMock()
        manager.add_observer(bad_observer)
        manager.add_observer(good_observer)

        manager.reload({"logging": {"level": "DEBUG"}})

        # Both were called despite the first raising
        bad_observer.assert_called_once()
        good_observer.assert_called_once()
        assert manager.config.logging.level == "DEBUG"


class TestConfigManagerThreadSafety:
    @pytest.mark.slow
    def test_concurrent_reads_and_writes(self, manager):
        """Verify no data corruption under concurrent access."""
        errors = []

        def writer():
            try:
                for level in ["DEBUG", "INFO", "WARNING", "ERROR"]:
                    manager.reload({"logging": {"level": level}})
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(10):
                    cfg = manager.config
                    assert cfg.logging.level in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(3)]
        threads += [threading.Thread(target=reader) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
