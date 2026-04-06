"""Unit tests for LangGraph agent."""

from unittest.mock import Mock, patch, MagicMock

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
        assert Severity.CRITICAL >= Severity.HIGH
        assert not (Severity.LOW >= Severity.MEDIUM)


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

    def test_sensor_monitor_partial_threshold_override(self, agent_config):
        agent_config["severity_thresholds"] = {"critical": 0.95}
        agent = TricorderAgent(config=agent_config)
        state: AgentState = {
            "messages": [],
            "anomaly_event": {"anomaly_score": 0.8},
            "evidence": [],
            "planned_tools": [],
            "tool_results": [],
            "report": None,
            "severity": None,
            "needs_human_approval": False,
            "iteration_count": 0,
        }
        result = agent.sensor_monitor_node(state)
        assert result["severity"] == "HIGH"

    def test_sensor_monitor_invalid_thresholds_fallback(self, agent_config):
        agent_config["severity_thresholds"] = "invalid"
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

    def test_build_graph_with_langgraph(self, agent_config):
        """Test build_graph when langgraph is available (mocked)."""
        import sys

        agent = TricorderAgent(config=agent_config)

        mock_compiled = MagicMock()
        mock_graph_instance = MagicMock()
        mock_graph_instance.compile.return_value = mock_compiled

        mock_state_graph = MagicMock(return_value=mock_graph_instance)
        mock_end = "END_SENTINEL"

        mock_langgraph_graph = MagicMock()
        mock_langgraph_graph.StateGraph = mock_state_graph
        mock_langgraph_graph.END = mock_end

        # Inject mock langgraph modules into sys.modules
        orig_lg = sys.modules.get("langgraph")
        orig_lg_graph = sys.modules.get("langgraph.graph")
        try:
            sys.modules["langgraph"] = MagicMock()
            sys.modules["langgraph.graph"] = mock_langgraph_graph

            result = agent.build_graph()

            assert result == mock_compiled
            assert agent._graph == mock_compiled
            mock_state_graph.assert_called_once_with(AgentState)
            assert mock_graph_instance.add_node.call_count == 5
            mock_graph_instance.compile.assert_called_once()
        finally:
            # Restore original module state
            if orig_lg is None:
                sys.modules.pop("langgraph", None)
            else:
                sys.modules["langgraph"] = orig_lg
            if orig_lg_graph is None:
                sys.modules.pop("langgraph.graph", None)
            else:
                sys.modules["langgraph.graph"] = orig_lg_graph

    def test_run_with_compiled_graph(self, agent_config):
        """Test run() when a compiled graph is available (not 'standalone')."""
        agent = TricorderAgent(config=agent_config)

        mock_result = {
            "messages": [{"role": "assistant", "content": "done"}],
            "report": "## Test Report",
            "severity": "LOW",
        }
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = mock_result
        agent._graph = mock_graph

        event = {"anomaly_score": 0.3}
        result = agent.run(event)
        assert result == mock_result
        mock_graph.invoke.assert_called_once()

    def test_run_graph_invoke_failure_falls_back(self, agent_config):
        """If graph.invoke raises, fallback to sequential execution."""
        agent = TricorderAgent(config=agent_config)

        mock_graph = MagicMock()
        mock_graph.invoke.side_effect = RuntimeError("Graph failed")
        agent._graph = mock_graph

        event = {"anomaly_score": 0.5, "affected_sensors": ["s1"]}
        result = agent.run(event)
        # Should still produce a report via fallback
        assert result["report"] is not None
        assert result["severity"] is not None

    def test_execute_tools_caller_raises(self, agent_config):
        """Tool caller that raises an exception records failure."""
        mock_caller = Mock(side_effect=Exception("Tool error"))
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
        assert result["tool_results"][0]["success"] is False
        assert "Tool error" in result["tool_results"][0]["error"]

    def test_sensor_monitor_medium_severity(self, agent_config):
        """Test MEDIUM severity classification."""
        agent = TricorderAgent(config=agent_config)
        state: AgentState = {
            "messages": [],
            "anomaly_event": {"anomaly_score": 0.6},
            "evidence": [],
            "planned_tools": [],
            "tool_results": [],
            "report": None,
            "severity": None,
            "needs_human_approval": False,
            "iteration_count": 0,
        }
        result = agent.sensor_monitor_node(state)
        assert result["severity"] == "MEDIUM"

    def test_sensor_monitor_high_severity(self, agent_config):
        """Test HIGH severity classification."""
        agent = TricorderAgent(config=agent_config)
        state: AgentState = {
            "messages": [],
            "anomaly_event": {"anomaly_score": 0.8},
            "evidence": [],
            "planned_tools": [],
            "tool_results": [],
            "report": None,
            "severity": None,
            "needs_human_approval": False,
            "iteration_count": 0,
        }
        result = agent.sensor_monitor_node(state)
        assert result["severity"] == "HIGH"


class TestAgentMain:
    def test_main_function(self):
        """Test the main() entry point."""
        from agents.langgraph_agent import main

        mock_config = MagicMock()
        mock_config.agent.model_dump.return_value = {
            "llm_endpoint": "http://localhost:11434",
            "model_name": "test",
            "temperature": 0.1,
            "max_tokens": 512,
            "mission_mode": "patrol",
            "human_in_loop_threshold": "HIGH",
        }

        with patch("utils.config.load_config", return_value=mock_config):
            with patch("builtins.print") as mock_print:
                main()
                mock_print.assert_called_once()
                printed = mock_print.call_args[0][0]
                assert "Tricorder" in printed or "Situation" in printed
