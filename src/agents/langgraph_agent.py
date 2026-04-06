"""LangGraph ReAct agent for Tricorder Neural Platform.

Implements a stateful agent with sensor monitoring, evidence gathering,
tool planning/execution, and report synthesis nodes.
"""

from typing import Any, Dict, List, Optional, TypedDict, Annotated, cast
from datetime import datetime, timezone
from enum import Enum
import logging
import operator

logger = logging.getLogger(__name__)


class AgentError(Exception):
    """Base exception for agent-related errors."""
    pass


class AgentToolError(AgentError):
    """Raised when an agent tool call fails."""
    pass


class AgentTimeoutError(AgentError):
    """Raised when the agent exceeds iteration or time limits."""
    pass


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

    def __ge__(self, other: "Severity") -> bool:
        order = [self.LOW, self.MEDIUM, self.HIGH, self.CRITICAL]
        return order.index(self) >= order.index(other)


class AgentState(TypedDict, total=False):
    """State schema for the LangGraph agent."""
    messages: Annotated[List[Dict[str, Any]], operator.add]
    anomaly_event: Optional[Dict[str, Any]]
    evidence: Annotated[List[Dict[str, Any]], operator.add]
    planned_tools: List[str]
    planned_steps: List[Dict[str, Any]]
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

    DEFAULT_SEVERITY_THRESHOLDS = {
        "critical": 0.9,
        "high": 0.75,
        "medium": 0.5,
    }
    SEVERITY_LEVELS = ("critical", "high", "medium")
    DEFAULT_MAX_TOOLS_PER_ITERATION = 3
    DEFAULT_MAX_ITERATIONS = 5

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
        self.severity_thresholds = self._normalize_severity_thresholds(
            config.get("severity_thresholds")
        )
        self.max_tools_per_iteration = self._normalize_positive_int(
            config.get("max_tools_per_iteration"), self.DEFAULT_MAX_TOOLS_PER_ITERATION
        )
        self.max_iterations = self._normalize_positive_int(
            config.get("max_iterations"), self.DEFAULT_MAX_ITERATIONS
        )
        self.tool_caller = tool_caller
        self._graph: Any = None
        logger.info("TricorderAgent created: mode=%s, model=%s",
                     self.mission_mode, self.model_name)

    @classmethod
    def _normalize_severity_thresholds(cls, raw: Any) -> Dict[str, float]:
        defaults = dict(cls.DEFAULT_SEVERITY_THRESHOLDS)
        if raw is None:
            return defaults
        if not isinstance(raw, dict):
            logger.warning(
                "Invalid severity_thresholds type: %s; using defaults", type(raw).__name__
            )
            return defaults

        normalized = defaults.copy()
        try:
            for level in cls.SEVERITY_LEVELS:
                if level in raw:
                    normalized[level] = float(raw[level])
        except (TypeError, ValueError):
            logger.warning("Invalid severity_thresholds values; using defaults")
            return defaults

        if any(not 0.0 <= value <= 1.0 for value in normalized.values()):
            logger.warning("severity_thresholds values must be in [0.0, 1.0]; using defaults")
            return defaults

        if not (
            normalized["critical"] >= normalized["high"] >= normalized["medium"]
        ):
            logger.warning(
                "severity_thresholds must satisfy critical >= high >= medium; using defaults"
            )
            return defaults

        return normalized

    @staticmethod
    def _normalize_positive_int(raw: Any, default: int) -> int:
        if raw is None:
            return default
        try:
            value = int(raw)
        except (TypeError, ValueError):
            logger.warning("Invalid integer config value %r; using default=%d", raw, default)
            return default
        if value <= 0:
            logger.warning("Non-positive integer config value %d; using default=%d", value, default)
            return default
        return value

    def build_graph(self) -> Any:
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

    def _build_standalone_graph(self) -> str:
        """Fallback graph without langgraph dependency."""
        self._graph = "standalone"
        return self._graph

    def sensor_monitor_node(self, state: AgentState) -> Dict[str, Any]:
        """Entry node: receive and classify anomaly event."""
        event_raw = state.get("anomaly_event", {})
        event = event_raw if isinstance(event_raw, dict) else {}
        anomaly_score = event.get("anomaly_score", 0.0)

        sorted_thresholds = sorted(
            self.severity_thresholds.items(), key=lambda item: item[1], reverse=True
        )
        severity = Severity.LOW
        for level, threshold in sorted_thresholds:
            if anomaly_score >= threshold:
                severity = Severity.from_string(level)
                break

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
        event_raw = state.get("anomaly_event", {})
        event = event_raw if isinstance(event_raw, dict) else {}
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
            "planned_steps": list(evidence_plan),
            "evidence": evidence_plan,
        }

    def plan_tools_node(self, state: AgentState) -> Dict[str, Any]:
        """Plan which tools to execute next."""
        planned_steps = state.get("planned_steps", [])
        if planned_steps:
            executed_keys = set()
            for r in state.get("tool_results", []):
                t = r.get("tool", "")
                a = r.get("args", {}) if isinstance(r.get("args"), dict) else {}
                executed_keys.add((t, tuple(sorted((k, str(v)) for k, v in a.items()))))
            remaining_steps = [
                step for step in planned_steps
                if (
                    step.get("tool", ""),
                    tuple(sorted((k, str(v)) for k, v in step.get("args", {}).items())),
                ) not in executed_keys
            ]
            return {
                "planned_tools": [s["tool"] for s in remaining_steps],
                "planned_steps": remaining_steps,
            }
        # Fallback: no planned_steps, use name-only dedup (backward compat)
        planned = state.get("planned_tools", [])
        executed = [r.get("tool") for r in state.get("tool_results", [])]
        remaining = [t for t in planned if t not in executed]
        return {"planned_tools": remaining}

    def execute_tools_node(self, state: AgentState) -> Dict[str, Any]:
        """Execute planned tools via MCP tool caller."""
        planned_steps = state.get("planned_steps", [])
        planned = state.get("planned_tools", [])
        results = []

        if planned_steps:
            steps_to_run = planned_steps[:self.max_tools_per_iteration]
        else:
            steps_to_run = [{"tool": t, "args": {}} for t in planned[:self.max_tools_per_iteration]]

        for step in steps_to_run:
            tool_name = str(step.get("tool", ""))
            args = step.get("args", {})
            if not isinstance(args, dict):
                args = {}
            if self.tool_caller:
                try:
                    result = self.tool_caller(tool_name, args)
                    results.append({"tool": tool_name, "args": args, "result": result, "success": True})
                except Exception as e:
                    results.append({"tool": tool_name, "args": args, "error": str(e), "success": False})
            else:
                results.append({
                    "tool": tool_name,
                    "args": args,
                    "result": {"note": "No tool_caller configured"},
                    "success": False,
                })

        iteration = state.get("iteration_count", 0) + 1
        return {"tool_results": results, "iteration_count": iteration}

    def _should_continue(self, state: AgentState) -> str:
        """Decide whether to continue gathering or synthesize report."""
        iteration = state.get("iteration_count", 0)
        remaining = state.get("planned_tools", [])
        if remaining and iteration < self.max_iterations:
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
            "planned_steps": [],
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

        def merge_state(state: AgentState, updates: Dict[str, Any]) -> None:
            """Merge updates, accumulating Annotated list fields."""
            mutable_state = cast(Dict[str, Any], state)
            for key, value in updates.items():
                if key in ("messages", "evidence", "tool_results") and isinstance(value, list):
                    existing = mutable_state.get(key, [])
                    if not isinstance(existing, list):
                        existing = []
                    mutable_state[key] = existing + value
                else:
                    mutable_state[key] = value

        merge_state(state, self.sensor_monitor_node(state))
        merge_state(state, self.evidence_gather_node(state))
        merge_state(state, self.plan_tools_node(state))

        for _ in range(self.max_iterations):
            merge_state(state, self.execute_tools_node(state))
            decision = self._should_continue(state)
            if decision == "synthesize":
                break
            merge_state(state, self.plan_tools_node(state))
        else:
            # Loop exhausted without a "synthesize" decision — log timeout warning
            logger.warning(
                "Agent reached max_iterations=%d without completing; forcing synthesis",
                self.max_iterations,
            )
            cast(Dict[str, Any], state)["_timeout"] = AgentTimeoutError(
                f"Agent did not complete within {self.max_iterations} iterations"
            )

        merge_state(state, self.synthesize_report_node(state))
        return dict(state)


def main() -> None:
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
    logger.info("Agent report: %s", result.get("report", "No report generated"))


if __name__ == "__main__":
    main()
