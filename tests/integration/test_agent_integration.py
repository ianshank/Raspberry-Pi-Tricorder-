"""Integration tests for agent with tool calling."""

from unittest.mock import Mock

import pytest

from agents.langgraph_agent import TricorderAgent


@pytest.mark.integration
class TestAgentWithTools:
    def test_agent_calls_tools(self, agent_config):
        """Agent executes tool calls via injected caller."""
        tool_results = {
            "read_sensor": {"temperature_c": 25.0},
            "get_sensor_diagnostics": {"status": "ready"},
        }
        mock_caller = Mock(side_effect=lambda name, args: tool_results.get(name, {}))

        agent = TricorderAgent(config=agent_config, tool_caller=mock_caller)
        result = agent.run({
            "anomaly_score": 0.6,
            "affected_sensors": ["bme680_01"],
        })

        assert result["report"] is not None
        assert mock_caller.call_count > 0

    def test_agent_handles_tool_errors(self, agent_config):
        """Agent handles tool caller exceptions gracefully."""
        mock_caller = Mock(side_effect=RuntimeError("tool down"))
        agent = TricorderAgent(config=agent_config, tool_caller=mock_caller)

        result = agent.run({
            "anomaly_score": 0.8,
            "affected_sensors": ["sensor_a"],
        })

        assert result["report"] is not None
        # At least one tool result should be recorded
        all_results = result.get("tool_results", [])
        assert len(all_results) > 0
        # All calls should have failed since caller raises
        for r in all_results:
            assert r.get("success") is False

    def test_agent_no_affected_sensors(self, agent_config):
        """Agent with no affected sensors still produces report."""
        agent = TricorderAgent(config=agent_config)
        result = agent.run({"anomaly_score": 0.3})
        assert result["report"] is not None
        assert result["severity"] == "LOW"

    def test_agent_critical_needs_human(self, agent_config):
        """Critical severity triggers human-in-loop flag."""
        agent = TricorderAgent(config=agent_config)
        result = agent.run({"anomaly_score": 0.95})
        assert result["needs_human_approval"] is True

    def test_different_mission_modes(self):
        """Agent respects mission mode in reports."""
        for mode in ["patrol", "investigation", "cbrn", "maintenance"]:
            config = {
                "llm_endpoint": "http://localhost:11434",
                "model_name": "qwen2.5:3b",
                "temperature": 0.1,
                "max_tokens": 512,
                "mission_mode": mode,
                "human_in_loop_threshold": "HIGH",
            }
            agent = TricorderAgent(config=config)
            result = agent.run({"anomaly_score": 0.5})
            assert mode in result["report"]
