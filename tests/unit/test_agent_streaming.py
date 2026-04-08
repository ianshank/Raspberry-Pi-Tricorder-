"""Tests for TricorderAgent.run_streaming() SSE event generation."""

import pytest

from agents.langgraph_agent import TricorderAgent
from agents.llm_client import MockLLMClient


# Fixtures: agent_config, mock_tool_caller, anomaly_event from conftest.py


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
    async def test_node_event_order(self, agent_config, mock_tool_caller, anomaly_event):
        """Node enter events are emitted in the correct pipeline order."""
        agent = TricorderAgent(config=agent_config, tool_caller=mock_tool_caller)
        agent.build_graph()

        node_events = []
        async for event in agent.run_streaming(anomaly_event):
            if event["event"] == "node_enter":
                node_events.append(event["data"]["node"])

        # Verify ordering: sensor_monitor must come before evidence_gather, etc.
        sm_idx = node_events.index("sensor_monitor")
        eg_idx = node_events.index("evidence_gather")
        pt_idx = node_events.index("plan_tools")
        sr_idx = node_events.index("synthesize_report")
        assert sm_idx < eg_idx < pt_idx < sr_idx

    @pytest.mark.asyncio
    async def test_all_events_have_required_keys(self, agent_config, mock_tool_caller, anomaly_event):
        """Every yielded event dict has 'event' and 'data' keys."""
        agent = TricorderAgent(config=agent_config, tool_caller=mock_tool_caller)
        agent.build_graph()

        async for event in agent.run_streaming(anomaly_event):
            assert "event" in event, f"Missing 'event' key in {event}"
            assert "data" in event, f"Missing 'data' key in {event}"

    @pytest.mark.asyncio
    async def test_complete_is_last_event(self, agent_config, mock_tool_caller, anomaly_event):
        """The 'complete' event is always the last event emitted."""
        agent = TricorderAgent(config=agent_config, tool_caller=mock_tool_caller)
        agent.build_graph()

        events = []
        async for event in agent.run_streaming(anomaly_event):
            events.append(event)

        assert events[-1]["event"] == "complete"

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
        assert combined == "Token one two three"

    @pytest.mark.asyncio
    async def test_tokens_emitted_before_complete(self, agent_config, mock_tool_caller, anomaly_event):
        """Token events precede the final complete event."""
        llm_client = MockLLMClient(response="A B C")
        agent = TricorderAgent(
            config=agent_config,
            tool_caller=mock_tool_caller,
            llm_client=llm_client,
        )
        agent.build_graph()

        event_types = []
        async for event in agent.run_streaming(anomaly_event):
            event_types.append(event["event"])

        first_token_idx = event_types.index("token")
        complete_idx = event_types.index("complete")
        assert first_token_idx < complete_idx

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

    @pytest.mark.asyncio
    @pytest.mark.parametrize("score,expected_sev", [
        (0.2, "LOW"),
        (0.55, "MEDIUM"),
        (0.8, "HIGH"),
        (0.95, "CRITICAL"),
    ])
    async def test_severity_from_anomaly_score(
        self, agent_config, mock_tool_caller, score, expected_sev,
    ):
        """Streamed severity matches the anomaly score classification."""
        event_data = {
            "anomaly_score": score,
            "affected_sensors": ["bme680"],
            "timestamp": "2026-01-01T00:00:00Z",
        }
        agent = TricorderAgent(config=agent_config, tool_caller=mock_tool_caller)
        agent.build_graph()

        async for event in agent.run_streaming(event_data):
            if event["event"] == "complete":
                assert event["data"]["severity"] == expected_sev
                break
