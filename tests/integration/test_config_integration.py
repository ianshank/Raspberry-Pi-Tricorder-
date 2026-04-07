"""Integration tests for config loading from YAML and env vars."""
from __future__ import annotations

import pytest

from utils.config import load_config


@pytest.mark.integration
class TestConfigIntegration:
    def test_base_yaml_loads_all_sections(self):
        config = load_config()
        assert config.project_name is not None
        assert config.mcp_server is not None
        assert config.agent is not None
        assert config.ui is not None
        assert config.logging is not None
        assert config.feature_flags is not None

    def test_env_var_overrides_yaml(self, monkeypatch):
        monkeypatch.setenv("TRICORDER__LOGGING__LEVEL", "DEBUG")
        config = load_config()
        assert config.logging.level == "DEBUG"

    def test_nested_env_var_with_underscored_field(self, monkeypatch):
        monkeypatch.setenv("TRICORDER__MCP_SERVER__HOST", "192.168.1.100")
        config = load_config()
        assert config.mcp_server.host == "192.168.1.100"

    def test_boolean_env_var_parsed(self, monkeypatch):
        monkeypatch.setenv("TRICORDER__FEATURE_FLAGS__LLM_ENABLED", "true")
        config = load_config()
        assert config.feature_flags.llm_enabled is True
