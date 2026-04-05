"""Unit tests for LangGraph agent."""

import pytest
from unittest.mock import Mock

from agents.langgraph_agent import TricorderAgent, Severity, AgentState


class TestSeverity:
    def test_from_string(self):
        assert Severity.from_string("LOW") == Severity.LOW
        assert Severity.from_string("CRITICAL") == Severity.CRITICAL

    def test_from_string_case_insensitive(self):
        assert Severity.from_string("high") == Severity.HIGH

    def test_from_string_invalid(self):
        assert Severity.from_string("invalid") == Severity.LOW

    def test_comparison(self):
        assert Severity.HIGH >= Severity.MEDIUM
        assert Severity.CRITICAL > Severity.HIGH
        assert not (Severity.LOW > Severity.MEDIUM)


class TestTricorderAgent:
    def test_create(self, agent_config):
        agent = TricorderAgent(config=agent_config)
        assert agent.mission_mode == "patrol"
        assert agent.model_name == "qwen2.5:3b"

    def test_sensor_monitor_node_critical(self, agent_config):
        agent = TricorderAgent(config=agent_config)
        state: AgentState = {
            "messages": [],
            "anomaly_event": {"anomaly_score": 0.95},
            "evidence": [],
            "planned_tools": [],
            "tool_results": [],
            "report": None,
            "severity": None,
            "needs_human_approval": False,
            "iteration_count": 0,
        }
        result = agent.sensor_monitor_node(state)
        assert result["severity"] == "CRITICAL"
        assert result["needs_human_approval"] is True

    def test_sensor_monitor_node_low(self, agent_config):
        agent = TricorderAgent(config=agent_config)
        state: AgentState = {
            "messages": [],
            "anomaly_event": {"anomaly_score": 0.2},
            "evidence": [],
            "planned_tools": [],
            "tool_results": [],
            "report": None,
            "severity": None,
            "needs_human_approval": False,
            "iteration_count": 0,
        }
        result = agent.sensor_monitor_node(state)
        assert result["severity"] == "LOW"
        assert result["needs_human_approval"] is False

    def test_evidence_gather_node(self, agent_config):
        agent = TricorderAgent(config=agent_config)
        state: AgentState = {
            "messages": [],
            "anomaly_event": {"affected_sensors": ["bme680_01", "gas_mq2"]},
            "evidence": [],
            "planned_tools": [],
            "tool_results": [],
            "report": None,
            "severity": "HIGH",
            "needs_human_approval": False,
            "iteration_count": 0,
        }
        result = agent.evidence_gather_node(state)
        assert len(result["planned_tools"]) > 0
        assert "read_sensor" in result["planned_tools"]

    def test_plan_tools_node(self, agent_config):
        agent = TricorderAgent(config=agent_config)
        state: AgentState = {
            "messages": [],
            "anomaly_event": {},
            "evidence": [],
            "planned_tools": ["read_sensor", "get_sensor_diagnostics"],
            "tool_results": [{"tool": "read_sensor"}],
            "report": None,
            "severity": None,
            "needs_human_approval": False,
            "iteration_count": 0,
        }
        result = agent.plan_tools_node(state)
        assert "read_sensor" not in result["planned_tools"]
        assert "get_sensor_diagnostics" in result["planned_tools"]

    def test_execute_tools_no_caller(self, agent_config):
        agent = TricorderAgent(config=agent_config)
        state: AgentState = {
            "messages": [],
            "anomaly_event": {},
            "evidence": [],
            "planned_tools": ["read_sensor"],
            "tool_results": [],
            "report": None,
            "severity": None,
            "needs_human_approval": False,
            "iteration_count": 0,
        }
        result = agent.execute_tools_node(state)
        assert len(result["tool_results"]) == 1
        assert result["tool_results"][0]["success"] is False

    def test_execute_tools_with_caller(self, agent_config):
        mock_caller = Mock(return_value={"data": "ok"})
        agent = TricorderAgent(config=agent_config, tool_caller=mock_caller)
        state: AgentState = {
            "messages": [],
            "anomaly_event": {},
            "evidence": [],
            "planned_tools": ["read_sensor"],
            "tool_results": [],
            "report": None,
            "severity": None,
            "needs_human_approval": False,
            "iteration_count": 0,
        }
        result = agent.execute_tools_node(state)
        assert result["tool_results"][0]["success"] is True
        mock_caller.assert_called_once()

    def test_should_continue(self, agent_config):
        agent = TricorderAgent(config=agent_config)
        # Has remaining tools, low iteration
        state = {"planned_tools": ["tool_a"], "iteration_count": 1}
        assert agent._should_continue(state) == "continue"
        # No remaining tools
        state = {"planned_tools": [], "iteration_count": 1}
        assert agent._should_continue(state) == "synthesize"
        # Max iterations reached
        state = {"planned_tools": ["tool_a"], "iteration_count": 5}
        assert agent._should_continue(state) == "synthesize"

    def test_synthesize_report(self, agent_config):
        agent = TricorderAgent(config=agent_config)
        state: AgentState = {
            "messages": [],
            "anomaly_event": {},
            "evidence": [],
            "planned_tools": [],
            "tool_results": [
                {"tool": "read_sensor", "success": True},
                {"tool": "get_sensor_diagnostics", "success": False},
            ],
            "report": None,
            "severity": "HIGH",
            "needs_human_approval": False,
            "iteration_count": 2,
        }
        result = agent.synthesize_report_node(state)
        assert result["report"] is not None
        assert "HIGH" in result["report"]
        assert "read_sensor" in result["report"]

    def test_full_run_fallback(self, agent_config):
        agent = TricorderAgent(config=agent_config)
        event = {
            "anomaly_score": 0.82,
            "affected_sensors": ["bme680_01"],
        }
        result = agent.run(event)
        assert result["report"] is not None
        assert result["severity"] == "HIGH"

    def test_build_graph_standalone(self, agent_config):
        agent = TricorderAgent(config=agent_config)
        graph = agent._build_standalone_graph()
        assert graph == "standalone"

    def test_mission_mode_in_report(self, agent_config):
        agent_config["mission_mode"] = "cbrn"
        agent = TricorderAgent(config=agent_config)
        state: AgentState = {
            "messages": [],
            "anomaly_event": {},
            "evidence": [],
            "planned_tools": [],
            "tool_results": [],
            "report": None,
            "severity": "LOW",
            "needs_human_approval": False,
            "iteration_count": 0,
        }
        result = agent.synthesize_report_node(state)
        assert "cbrn" in result["report"]
