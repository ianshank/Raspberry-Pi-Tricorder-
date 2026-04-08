"""Tests for TricorderAgent.run_streaming() SSE event generation."""

import pytest

from agents.langgraph_agent import TricorderAgent
from agents.llm_client import MockLLMClient


@pytest.fixture
def agent_config():
    return {
        "llm_endpoint": "http://localhost:11434",
        "model_name": "test",
        "temperature": 0.1,
        "max_tokens": 512,
        "mission_mode": "patrol",
        "human_in_loop_threshold": "HIGH",
        "max_iterations": 2,
    }


@pytest.fixture
def mock_tool_caller():
    def caller(name, args):
        return {"sensor_id": args.get("sensor_id", "test"), "value": 42.0}
    return caller


@pytest.fixture
def anomaly_event():
    return {
        "anomaly_score": 0.8,
        "affected_sensors": ["bme680"],
        "timestamp": "2026-01-01T00:00:00Z",
    }


class TestRunStreaming:
    @pytest.mark.asyncio
    async def test_yields_node_enter_events(self, agent_config, mock_tool_caller, anomaly_event):
        agent = TricorderAgent(config=agent_config, tool_caller=mock_tool_caller)
        agent.build_graph()

        node_events = []
        async for event in agent.run_streaming(anomaly_event):
            if event["event"] == "node_enter":
                node_events.append(event["data"]["node"])

        assert "sensor_monitor" in node_events
        assert "evidence_gather" in node_events
        assert "plan_tools" in node_events
        assert "synthesize_report" in node_events

    @pytest.mark.asyncio
    async def test_yields_complete_event(self, agent_config, mock_tool_caller, anomaly_event):
        agent = TricorderAgent(config=agent_config, tool_caller=mock_tool_caller)
        agent.build_graph()

        complete_events = []
        async for event in agent.run_streaming(anomaly_event):
            if event["event"] == "complete":
                complete_events.append(event)

        assert len(complete_events) == 1
        assert "report" in complete_events[0]["data"]
        assert "severity" in complete_events[0]["data"]

    @pytest.mark.asyncio
    async def test_streams_llm_tokens(self, agent_config, mock_tool_caller, anomaly_event):
        llm_client = MockLLMClient(response="Token one two three")
        agent = TricorderAgent(
            config=agent_config,
            tool_caller=mock_tool_caller,
            llm_client=llm_client,
        )
        agent.build_graph()

        token_events = []
        async for event in agent.run_streaming(anomaly_event):
            if event["event"] == "token":
                token_events.append(event["data"]["text"])

        assert len(token_events) > 0
        combined = "".join(token_events).strip()
        assert "Token" in combined

    @pytest.mark.asyncio
    async def test_template_fallback_without_llm(self, agent_config, mock_tool_caller, anomaly_event):
        agent = TricorderAgent(config=agent_config, tool_caller=mock_tool_caller)
        agent.build_graph()

        complete = None
        token_events = []
        async for event in agent.run_streaming(anomaly_event):
            if event["event"] == "complete":
                complete = event
            elif event["event"] == "token":
                token_events.append(event)

        assert complete is not None
        assert "Situation Report" in complete["data"]["report"]
        assert token_events == []  # No tokens without LLM

    @pytest.mark.asyncio
    async def test_complete_contains_severity(self, agent_config, mock_tool_caller, anomaly_event):
        agent = TricorderAgent(config=agent_config, tool_caller=mock_tool_caller)
        agent.build_graph()

        async for event in agent.run_streaming(anomaly_event):
            if event["event"] == "complete":
                assert event["data"]["severity"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
                break
