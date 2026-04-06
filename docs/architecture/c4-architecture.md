# C4 Architecture - Tricorder Neural Platform

This document captures the C4 model views for the Raspberry Pi Tricorder application.
Last updated: 2026-04-06

---

## C1 - System Context

```mermaid
graph TB
    Operator["Field Operator\n(browser / keyboard)"]
    Hardware["Sensors + Hailo-10H Edge Hardware\n(I2C / SPI / UART)"]
    Tricorder["Tricorder Neural Platform\n(Raspberry Pi 5)"]
    Repo["GitHub + CI\n(Actions: lint, mypy, pytest)"]

    Operator -->|"Monitors telemetry,\nasks questions,\nacks anomalies"| Tricorder
    Hardware -->|"Raw telemetry\n& model inputs"| Tricorder
    Tricorder -->|"Health, reports\n& acknowledged events"| Operator
    Repo -->|"Automated build\n& test gating"| Tricorder
```

### Context Notes

- Primary user is a field operator using the LCARS web UI for telemetry monitoring and anomaly triage.
- Seven physical sensor types feed data through hardware-abstracted Python drivers.
- Neural models perform anomaly detection and multi-sensor fusion on the Hailo-10H NPU.
- The MCP server is the single integration backbone for tools, streaming, chat, and static UI.
- CI gates ruff (lint), mypy (types), and pytest (coverage ≥ 85%) on every push and PR.

---

## C2 - Container View

```mermaid
graph LR
    subgraph Browser["Browser (LCARS UI)"]
        UI["Static Web App\nHTML · CSS · ES Modules"]
    end

    subgraph Pi["Raspberry Pi 5"]
        MCP["FastAPI MCP Server\nTool APIs · WebSockets · UI APIs"]
        Agent["LangGraph ReAct Agent\nEvidence gather · Tool plan/exec · Report synthesis"]
        Models["ML Models\nAnomaly detector · Fusion engine"]
        Sensors["Sensor Layer\n7 drivers · Manager · SimulatedSensor"]
        Config["Config + Logging\nYAML · Pydantic · env-var overrides"]
    end

    UI <-->|"HTTP / WebSocket"| MCP
    MCP <-->|"Tool calls + args"| Agent
    MCP <-->|"Inference + history"| Models
    MCP <-->|"Readings + diagnostics"| Sensors
    MCP <-->|"Runtime settings"| Config
    Agent <-->|"Sensor + anomaly context\nvia ToolRegistry"| MCP
```

### Container Responsibilities

| Container | Responsibility |
|---|---|
| **Web UI** | Panelised LCARS telemetry; agent chat; anomaly ack workflow; markdown rendering |
| **MCP Server** | Integration backbone: ToolRegistry, WS streams, auth, anomaly tracking, 404/error handling |
| **LangGraph Agent** | `evidence_gather → plan_tools → execute_tools → synthesize_report` ReAct loop with per-tool args |
| **ML Models** | Autoencoder-LSTM anomaly detector; sensor fusion transformer (Hailo-10H targets) |
| **Sensor Layer** | Hardware-abstracted drivers + `_SimulatedSensor` for hardware-free development |
| **Config** | Pydantic-validated YAML config; zero hardcoded values; env-var overrides |

---

## C3 - Component View (MCP Server)

```mermaid
graph TB
    subgraph Routes["FastAPI Router Layer"]
        HealthR["GET /health"]
        ToolsR["GET /tools\nPOST /tools/call"]
        UIConfigR["GET /ui/config.json"]
        SensorWSR["WS /ws/sensors"]
        AnomalyWSR["WS /ws/anomalies"]
        AckR["GET+POST /ui/anomalies/ack"]
        ChatR["POST /ui/agent/chat"]
        StaticR["GET /ui/**\n(static files + HTML 404)"]
    end

    subgraph Services["Internal Services"]
        Registry["ToolRegistry\nRegister · Call · Schema"]
        Bootstrap["_bootstrap_default_tools()\nAuto-registers 7 tools\non startup"]
        SimSensor["_SimulatedSensor(BaseSensor)\nHardware-free dev sensor\nfor all 7 types"]
        UIConfig["UI Config Sanitizer\n_sanitize_ui_config()"]
        AnomalyTrack["Anomaly ACK Store\n_upsert_anomaly_ack()\ncapped by history_limit"]
        AuthMW["Auth Middleware\nBearertoken · HMAC compare_digest"]
        NotFound["Exception Handler\n404: HTML for /ui/*\nJSON for API paths"]
    end

    HealthR --> Registry
    ToolsR --> Registry
    UIConfigR --> UIConfig
    SensorWSR --> Registry
    AnomalyWSR --> Registry
    AnomalyWSR --> AnomalyTrack
    AckR --> AnomalyTrack
    ChatR --> Registry
    StaticR --> NotFound

    Bootstrap --> Registry
    Bootstrap --> SimSensor
    AuthMW --> ToolsR
    AuthMW --> AckR
    AuthMW --> ChatR
```

### Component Notes

- `ToolRegistry` encapsulates callable MCP tool functions, schemas, and sync/async dispatch.
- `_bootstrap_default_tools()` auto-registers all 7 sensor tools when no registry is injected,
  enabling the full UI and agent without hardware.
- `_SimulatedSensor(BaseSensor)` provides realistic randomised readings for all 7 sensor types
  so the complete sensor/anomaly/agent pipeline exercises without physical hardware.
- UI config sanitizer publishes safe runtime config; strips server-side secrets before sending.
- Auth middleware fails closed when auth is enabled but no API key is configured (HTTP 503).
- 404 handler returns LCARS-branded HTML for `/ui/*` paths and preserves `detail` on API paths.

---

## C3b - Component View (LangGraph Agent)

```mermaid
graph LR
    subgraph Nodes["Agent Nodes (ReAct Loop)"]
        SM["sensor_monitor\nEntry: classify anomaly\n& set severity"]
        EG["evidence_gather\nBuild planned_steps\nList[{tool, args, reason}]"]
        PT["plan_tools\nDedup by (tool,args) pair\ntrack remaining steps"]
        ET["execute_tools\nCall tool_caller(name, args)\nfor each planned step"]
        SR["synthesize_report\nGenerate markdown SITREP\nfrom evidence + results"]
    end

    SM --> EG --> PT --> ET
    ET -->|"remaining steps?"| PT
    PT -->|"done or max_iter"| SR

    subgraph State["AgentState (TypedDict)"]
        S1["messages · anomaly_event"]
        S2["evidence · planned_tools"]
        S3["planned_steps · tool_results"]
        S4["severity · iteration_count\nneeds_human_approval · report"]
    end
```

### Key Design Decisions

- `planned_steps: List[Dict]` carries `{tool, args}` pairs through the cycle; `planned_tools` retains the name-only list for backward compatibility with tests that check membership.
- Deduplication in `plan_tools_node` hashes `(tool_name, frozenset(args.items()))` so multiple `read_sensor` calls for different `sensor_id` values all execute independently.
- `synthesize_report_node` emits GitHub-flavoured markdown; the chat panel renders it via `renderMarkdown()`.

---

## C4 - Code View Anchors

| Concern | Entry Point |
|---|---|
| Server bootstrap & routing | `src/mcp_server/server.py` → `create_app()` |
| Tool registration | `src/mcp_server/server.py` → `_bootstrap_default_tools()` |
| Simulated hardware | `src/mcp_server/server.py` → `_SimulatedSensor` |
| Agent ReAct loop | `src/agents/langgraph_agent.py` → `TricorderAgent` |
| UI live data | `src/ui/static/js/services/data-service.js` → `DataService` |
| Anomaly alert rendering | `src/ui/static/js/components/anomaly-alert-stack.js` |
| Environmental telemetry | `src/ui/static/js/components/env-panel.js` |
| Biomedical + thermal | `src/ui/static/js/components/bio-panel.js` |
| Engineering / radar | `src/ui/static/js/components/eng-panel.js` |
| Markdown chat rendering | `src/ui/static/js/components/agent-chat-panel.js` |
| Pydantic configuration | `src/utils/config.py` |
| Anomaly detection model | `src/models/anomaly_detector.py` |
| Sensor driver base | `src/sensors/base.py` → `BaseSensor` |

---

## Roadmap Reference

Operational roadmap items are maintained in `README.md` under the **Next Steps** section.
