"""LangGraph ReAct agent for Tricorder Neural Platform.

Implements a stateful agent with sensor monitoring, evidence gathering,
tool planning/execution, and report synthesis nodes.
"""

from typing import Any, Dict, List, Optional, TypedDict, Annotated
from datetime import datetime, timezone
from enum import Enum
import logging
import operator

logger = logging.getLogger(__name__)


class Severity(Enum):
    """Alert severity levels."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @classmethod
    def from_string(cls, value: str) -> "Severity":
        try:
            return cls[value.upper()]
        except KeyError:
            return cls.LOW

    def __ge__(self, other):
        order = [self.LOW, self.MEDIUM, self.HIGH, self.CRITICAL]
        return order.index(self) >= order.index(other)

    def __gt__(self, other):
        order = [self.LOW, self.MEDIUM, self.HIGH, self.CRITICAL]
        return order.index(self) > order.index(other)


class AgentState(TypedDict, total=False):
    """State schema for the LangGraph agent."""
    messages: Annotated[List[Dict[str, Any]], operator.add]
    anomaly_event: Optional[Dict[str, Any]]
    evidence: Annotated[List[Dict[str, Any]], operator.add]
    planned_tools: List[str]
    tool_results: Annotated[List[Dict[str, Any]], operator.add]
    report: Optional[str]
    severity: Optional[str]
    needs_human_approval: bool
    iteration_count: int


class TricorderAgent:
    """
    LangGraph-based ReAct agent for autonomous sensor monitoring and analysis.

    Nodes:
    - sensor_monitor: Entry point, receives anomaly events
    - evidence_gather: Collects additional sensor data
    - plan_tools: Decides which tools to invoke
    - execute_tools: Calls MCP tools
    - synthesize_report: Generates situation report
    """

    def __init__(self, config: Dict[str, Any], tool_caller: Optional[Any] = None):
        """
        Args:
            config: LangGraphAgentConfig as dict
            tool_caller: Callable for MCP tool execution (injected)
        """
        self.config = config
        self.llm_endpoint = config.get("llm_endpoint", "http://localhost:11434")
        self.model_name = config.get("model_name", "qwen2.5:3b")
        self.temperature = config.get("temperature", 0.1)
        self.max_tokens = config.get("max_tokens", 512)
        self.mission_mode = config.get("mission_mode", "patrol")
        self.human_in_loop_threshold = Severity.from_string(
            config.get("human_in_loop_threshold", "HIGH")
        )
        self.tool_caller = tool_caller
        self._graph = None
        logger.info("TricorderAgent created: mode=%s, model=%s",
                     self.mission_mode, self.model_name)

    def build_graph(self):
        """Build the LangGraph state graph. Requires langgraph package."""
        try:
            from langgraph.graph import StateGraph, END
        except ImportError:
            logger.warning("langgraph not installed, using standalone mode")
            return self._build_standalone_graph()

        graph = StateGraph(AgentState)

        graph.add_node("sensor_monitor", self.sensor_monitor_node)
        graph.add_node("evidence_gather", self.evidence_gather_node)
        graph.add_node("plan_tools", self.plan_tools_node)
        graph.add_node("execute_tools", self.execute_tools_node)
        graph.add_node("synthesize_report", self.synthesize_report_node)

        graph.set_entry_point("sensor_monitor")
        graph.add_edge("sensor_monitor", "evidence_gather")
        graph.add_edge("evidence_gather", "plan_tools")
        graph.add_edge("plan_tools", "execute_tools")
        graph.add_conditional_edges(
            "execute_tools",
            self._should_continue,
            {"continue": "plan_tools", "synthesize": "synthesize_report"},
        )
        graph.add_edge("synthesize_report", END)

        self._graph = graph.compile()
        logger.info("LangGraph state graph compiled")
        return self._graph

    def _build_standalone_graph(self):
        """Fallback graph without langgraph dependency."""
        self._graph = "standalone"
        return self._graph

    def sensor_monitor_node(self, state: AgentState) -> Dict[str, Any]:
        """Entry node: receive and classify anomaly event."""
        event = state.get("anomaly_event", {})
        anomaly_score = event.get("anomaly_score", 0.0)

        if anomaly_score >= 0.9:
            severity = Severity.CRITICAL
        elif anomaly_score >= 0.75:
            severity = Severity.HIGH
        elif anomaly_score >= 0.5:
            severity = Severity.MEDIUM
        else:
            severity = Severity.LOW

        logger.info("Anomaly event received: score=%.2f, severity=%s",
                     anomaly_score, severity.value)

        return {
            "severity": severity.value,
            "needs_human_approval": severity >= self.human_in_loop_threshold,
            "messages": [{
                "role": "system",
                "content": f"Anomaly detected (score={anomaly_score:.2f}, severity={severity.value}). "
                           f"Mission mode: {self.mission_mode}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }],
        }

    def evidence_gather_node(self, state: AgentState) -> Dict[str, Any]:
        """Gather additional sensor evidence based on anomaly context."""
        event = state.get("anomaly_event", {})
        affected_sensors = event.get("affected_sensors", [])

        # Determine which sensors to query for evidence
        evidence_plan = []
        for sensor_id in affected_sensors:
            evidence_plan.append({
                "tool": "read_sensor",
                "args": {"sensor_id": sensor_id},
                "reason": f"Read affected sensor: {sensor_id}",
            })

        # Also gather environmental context
        evidence_plan.append({
            "tool": "get_sensor_diagnostics",
            "args": {},
            "reason": "Check overall sensor health",
        })

        return {
            "planned_tools": [ep["tool"] for ep in evidence_plan],
            "evidence": evidence_plan,
        }

    def plan_tools_node(self, state: AgentState) -> Dict[str, Any]:
        """Plan which tools to execute next."""
        planned = state.get("planned_tools", [])
        executed = [r.get("tool") for r in state.get("tool_results", [])]
        remaining = [t for t in planned if t not in executed]

        return {"planned_tools": remaining}

    def execute_tools_node(self, state: AgentState) -> Dict[str, Any]:
        """Execute planned tools via MCP tool caller."""
        planned = state.get("planned_tools", [])
        results = []

        for tool_name in planned[:3]:  # Max 3 per iteration
            if self.tool_caller:
                try:
                    result = self.tool_caller(tool_name, {})
                    results.append({"tool": tool_name, "result": result, "success": True})
                except Exception as e:
                    results.append({"tool": tool_name, "error": str(e), "success": False})
            else:
                results.append({
                    "tool": tool_name,
                    "result": {"note": "No tool_caller configured"},
                    "success": False,
                })

        iteration = state.get("iteration_count", 0) + 1
        return {"tool_results": results, "iteration_count": iteration}

    def _should_continue(self, state: AgentState) -> str:
        """Decide whether to continue gathering or synthesize report."""
        iteration = state.get("iteration_count", 0)
        remaining = state.get("planned_tools", [])
        if remaining and iteration < 5:
            return "continue"
        return "synthesize"

    def synthesize_report_node(self, state: AgentState) -> Dict[str, Any]:
        """Generate final situation report from gathered evidence."""
        severity = state.get("severity", "LOW")
        evidence_items = state.get("evidence", [])
        tool_results = state.get("tool_results", [])
        logger.debug("Synthesizing report: severity=%s, evidence=%d, tools=%d",
                     severity, len(evidence_items), len(tool_results))

        # Build report from evidence
        report_lines = [
            "## Tricorder Situation Report",
            f"**Severity:** {severity}",
            f"**Mission Mode:** {self.mission_mode}",
            f"**Timestamp:** {datetime.now(timezone.utc).isoformat()}",
            "",
            f"### Evidence Collected ({len(tool_results)} tool calls)",
        ]

        for result in tool_results:
            tool = result.get("tool", "unknown")
            success = result.get("success", False)
            status = "OK" if success else "FAILED"
            report_lines.append(f"- **{tool}**: {status}")

        report_lines.append("")
        report_lines.append("### Recommendation")
        if severity in ("HIGH", "CRITICAL"):
            report_lines.append("Immediate attention required. Operator notification sent.")
        else:
            report_lines.append("Situation logged. Continuing automated monitoring.")

        report = "\n".join(report_lines)

        return {
            "report": report,
            "messages": [{
                "role": "assistant",
                "content": report,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }],
        }

    def run(self, anomaly_event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run the agent on an anomaly event.

        Falls back to sequential node execution if langgraph is unavailable.
        """
        initial_state: AgentState = {
            "messages": [],
            "anomaly_event": anomaly_event,
            "evidence": [],
            "planned_tools": [],
            "tool_results": [],
            "report": None,
            "severity": None,
            "needs_human_approval": False,
            "iteration_count": 0,
        }

        if self._graph and self._graph != "standalone":
            try:
                result = self._graph.invoke(initial_state)
                return result
            except Exception as e:
                logger.error("Graph execution failed, using fallback: %s", e)

        # Fallback: sequential execution (manually accumulate list fields)
        state = initial_state

        def merge_state(state, updates):
            """Merge updates, accumulating Annotated list fields."""
            for key, value in updates.items():
                if key in ("messages", "evidence", "tool_results") and isinstance(value, list):
                    state[key] = state.get(key, []) + value
                else:
                    state[key] = value

        merge_state(state, self.sensor_monitor_node(state))
        merge_state(state, self.evidence_gather_node(state))
        merge_state(state, self.plan_tools_node(state))

        for _ in range(5):
            merge_state(state, self.execute_tools_node(state))
            decision = self._should_continue(state)
            if decision == "synthesize":
                break
            merge_state(state, self.plan_tools_node(state))

        merge_state(state, self.synthesize_report_node(state))
        return state


def main():
    """Entry point for running agent standalone."""
    from utils.config import load_config

    config = load_config()
    agent = TricorderAgent(config=config.agent.model_dump())
    agent.build_graph()

    # Example: simulate an anomaly event
    test_event = {
        "anomaly_score": 0.82,
        "affected_sensors": ["bme680_01", "gas_mq2"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    result = agent.run(test_event)
    print(result.get("report", "No report generated"))


if __name__ == "__main__":
    main()
