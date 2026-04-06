"""Tests covering previously-uncovered agent validation and timeout paths."""

from unittest.mock import Mock, patch

from agents.langgraph_agent import (
    TricorderAgent,
    AgentTimeoutError,
)


class TestNormalizeSeverityThresholds:
    """Covers lines 129-143 in langgraph_agent.py."""

    def test_none_returns_defaults(self):
        result = TricorderAgent._normalize_severity_thresholds(None)
        assert result == {"critical": 0.9, "high": 0.75, "medium": 0.5}

    def test_non_dict_returns_defaults(self):
        result = TricorderAgent._normalize_severity_thresholds("invalid")
        assert result == {"critical": 0.9, "high": 0.75, "medium": 0.5}

    def test_non_dict_list_returns_defaults(self):
        result = TricorderAgent._normalize_severity_thresholds([0.9, 0.75])
        assert result == {"critical": 0.9, "high": 0.75, "medium": 0.5}

    def test_valid_overrides(self):
        result = TricorderAgent._normalize_severity_thresholds(
            {"critical": 0.95, "high": 0.80, "medium": 0.6}
        )
        assert result["critical"] == 0.95
        assert result["high"] == 0.80
        assert result["medium"] == 0.6

    def test_non_numeric_value_falls_back_to_defaults(self):
        """Lines 129-131: TypeError/ValueError during float() cast."""
        result = TricorderAgent._normalize_severity_thresholds(
            {"critical": "very_high", "high": 0.75, "medium": 0.5}
        )
        assert result == {"critical": 0.9, "high": 0.75, "medium": 0.5}

    def test_none_value_falls_back_to_defaults(self):
        result = TricorderAgent._normalize_severity_thresholds(
            {"critical": None, "high": 0.75, "medium": 0.5}
        )
        assert result == {"critical": 0.9, "high": 0.75, "medium": 0.5}

    def test_value_above_one_falls_back_to_defaults(self):
        """Lines 133-135: value outside [0, 1]."""
        result = TricorderAgent._normalize_severity_thresholds(
            {"critical": 1.5, "high": 0.75, "medium": 0.5}
        )
        assert result == {"critical": 0.9, "high": 0.75, "medium": 0.5}

    def test_value_below_zero_falls_back_to_defaults(self):
        result = TricorderAgent._normalize_severity_thresholds(
            {"critical": 0.9, "high": -0.1, "medium": 0.5}
        )
        assert result == {"critical": 0.9, "high": 0.75, "medium": 0.5}

    def test_wrong_ordering_falls_back_to_defaults(self):
        """Lines 137-143: critical < high violates ordering constraint."""
        result = TricorderAgent._normalize_severity_thresholds(
            {"critical": 0.5, "high": 0.75, "medium": 0.9}
        )
        assert result == {"critical": 0.9, "high": 0.75, "medium": 0.5}

    def test_partial_override_keeps_defaults_for_missing(self):
        result = TricorderAgent._normalize_severity_thresholds({"critical": 0.95})
        assert result["critical"] == 0.95
        assert result["high"] == 0.75
        assert result["medium"] == 0.5


class TestNormalizePositiveInt:
    """Covers lines 153-158 in langgraph_agent.py."""

    def test_none_returns_default(self):
        assert TricorderAgent._normalize_positive_int(None, 5) == 5

    def test_valid_int(self):
        assert TricorderAgent._normalize_positive_int(10, 5) == 10

    def test_string_convertible(self):
        assert TricorderAgent._normalize_positive_int("7", 5) == 7

    def test_non_convertible_string_returns_default(self):
        """Line 153-155: ValueError path."""
        assert TricorderAgent._normalize_positive_int("abc", 5) == 5

    def test_float_string_truncates(self):
        # int("3.5") raises ValueError → default
        assert TricorderAgent._normalize_positive_int("3.5", 5) == 5

    def test_zero_returns_default(self):
        """Line 156-158: value <= 0 path."""
        assert TricorderAgent._normalize_positive_int(0, 5) == 5

    def test_negative_returns_default(self):
        assert TricorderAgent._normalize_positive_int(-3, 5) == 5

    def test_list_returns_default(self):
        """TypeError path when int([]) fails."""
        assert TricorderAgent._normalize_positive_int([], 3) == 3


class TestAgentRunTimeout:
    """Covers the for/else timeout path (formerly line 368 area)."""

    def test_max_iterations_exhausted_sets_timeout(self, agent_config):
        """When no tool produces 'synthesize', _timeout is set on state."""
        config = dict(agent_config)
        config["max_iterations"] = 1

        # Tool caller always returns empty result → agent never synthesizes
        agent = TricorderAgent(config=config, tool_caller=Mock(return_value={}))
        agent.build_graph()

        event = {
            "anomaly_score": 0.85,
            "affected_sensors": ["bme680_01"],
        }

        # patch _should_continue to always return "continue" (never synthesize)
        with patch.object(agent, "_should_continue", return_value="continue"):
            result = agent.run(event)

        assert "_timeout" in result
        assert isinstance(result["_timeout"], AgentTimeoutError)

    def test_successful_run_no_timeout(self, agent_config):
        """Normal run completes without setting _timeout."""
        agent = TricorderAgent(config=agent_config, tool_caller=Mock(return_value={}))
        agent.build_graph()
        event = {"anomaly_score": 0.5, "affected_sensors": []}
        result = agent.run(event)
        assert "_timeout" not in result
        assert "report" in result


class TestMergeStateNonListExisting:
    """Covers the isinstance(existing, list) guard inside merge_state (line 367)."""

    def test_merge_handles_non_list_messages(self, agent_config):
        """If existing state has a corrupted (non-list) messages field, it resets."""
        agent = TricorderAgent(config=agent_config, tool_caller=Mock(return_value={}))
        agent.build_graph()

        # Build initial state with corrupted messages field
        from agents.langgraph_agent import AgentState

        state: AgentState = {
            "messages": "corrupted",  # type: ignore[typeddict-item]
            "anomaly_event": {"anomaly_score": 0.5},
            "evidence": [],
            "planned_tools": [],
            "tool_results": [],
            "report": None,
            "severity": None,
            "needs_human_approval": False,
            "iteration_count": 0,
        }

        # Calling sensor_monitor_node should not crash even with corrupted messages
        result = agent.sensor_monitor_node(state)
        assert isinstance(result.get("messages", []), list)
