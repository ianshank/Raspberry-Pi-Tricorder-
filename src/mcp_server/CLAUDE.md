# MCP Server

## App Creation

The FastAPI app is created via `create_app(config, registry)` in `server.py`. Never instantiate `FastAPI()` directly elsewhere. Config comes from Pydantic models — no inline defaults in endpoint handlers.

## Tool Registry

Tools are registered via `ToolRegistry`:
- `register_sensor_tools(registry, sensor_manager)` — in `tools/sensor_tools.py`
- `register_anomaly_tools(registry, model_registry)` — in `tools/anomaly_tools.py`

Tool functions return dicts. Errors return `{"error": "message"}`. Use the `GENERIC_*_ERROR` constants for user-facing error messages.

## Module Organization

- `server.py` — FastAPI app, endpoints, WebSocket handlers, simulation registry
- `anomaly_helpers.py` — Pure functions: `coerce_float`, `coerce_bool`, `severity_from_score`, `extract_anomaly_summary`, `build_anomaly_id`
- `ui_helpers.py` — Pure functions: `display_label`, `build_query_intent_note`, `build_sensor_catalog`, `sanitize_ui_config`
- `tools/sensor_tools.py` — Sensor tool wrappers
- `tools/anomaly_tools.py` — Anomaly detection tool wrappers

## Simulation Registry

Simulated sensor values use `@_register_simulation("pattern")` decorator. To add a new simulated sensor, add a decorated function — do not modify `_build_simulated_sensor_value()`.

## Endpoints

- `GET /health` — Health check
- `POST /tools/call` — Execute a registered tool
- `GET /ui/config.json` — Sanitized UI configuration
- `WS /ws/sensors` — Real-time sensor streaming
- `WS /ws/anomalies` — Anomaly alert streaming
- `POST /ui/agent/chat` — Agent chat (when agent enabled)

## Auth

API key auth middleware with `PUBLIC_PATHS` allowlist. Configurable via `mcp_server.auth_enabled` and `mcp_server.api_key` in config.
