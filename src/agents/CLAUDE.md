# LangGraph ReAct Agent

## Architecture

The `TricorderAgent` implements a 5-node state machine:

```
sensor_monitor -> evidence_gather -> plan_tools -> execute_tools -> synthesize_report
```

Each node is a function that receives and returns `AgentState` (TypedDict).

## State Schema

Key fields in `AgentState`:
- `messages` — Conversation history (Annotated with operator.add)
- `anomaly_event` — Triggering anomaly data
- `evidence` — Gathered sensor evidence
- `planned_tools` / `planned_steps` — Tool execution plan
- `tool_results` — Execution results
- `report` — Final synthesized report
- `severity` — Severity enum (LOW, MEDIUM, HIGH, CRITICAL)
- `needs_human_approval` — Human-in-the-loop gate
- `iteration_count` — Loop counter for safety

## Severity

Severity thresholds are imported from `utils.constants.DEFAULT_SEVERITY_THRESHOLDS`. Never define thresholds inline — use the shared constants.

Severity levels: `SEVERITY_LEVELS = ("critical", "high", "medium")` from `utils.constants`.

## Human-in-the-Loop

When severity >= HIGH, `needs_human_approval` is set to True. The graph pauses for human confirmation before executing planned tools.

## Error Handling

Agent exceptions: `AgentError` (base), `AgentToolError` (tool failures), `AgentTimeoutError` (iteration/time limits). These are defined at the top of `langgraph_agent.py`.
