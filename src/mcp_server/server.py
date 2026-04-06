"""MCP Server for Tricorder Neural Platform.

Exposes sensor tools via FastAPI with dynamic tool registry.
All configuration loaded from TricorderConfig — no hardcoded values.
"""

from typing import Any, Awaitable, Callable, Dict, List, Optional
from datetime import datetime, timezone
import asyncio
import hmac
import hashlib
import logging
import math
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


DEFAULT_UI_WS_PATH = "/ws/sensors"
DEFAULT_UI_ANOMALY_WS_PATH = "/ws/anomalies"
DEFAULT_UI_ANOMALY_ACK_PATH = "/ui/anomalies/ack"
DEFAULT_UI_AGENT_CHAT_PATH = "/ui/agent/chat"
AUTH_PUBLIC_PATHS = {"/health", "/docs", "/openapi.json"}


class Tool(BaseModel):
    """MCP tool definition."""
    name: str
    description: str
    inputSchema: Dict[str, Any]


class ToolCallRequest(BaseModel):
    """Request to call a tool."""
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class ToolCallResponse(BaseModel):
    """Response from a tool call."""
    content: Any
    isError: bool = False


class AgentChatRequest(BaseModel):
    """Request payload for UI agent chat endpoint."""

    query: str = Field(..., min_length=1, max_length=4000)
    include_sensor_context: bool = Field(default=True)


class AnomalyAcknowledgeRequest(BaseModel):
    """Request payload for anomaly acknowledgment endpoint."""

    anomaly_id: str = Field(..., min_length=1, max_length=128)
    acknowledged_by: str = Field(default="ui", min_length=1, max_length=64)
    note: Optional[str] = Field(default=None, max_length=256)


class ToolRegistry:
    """Dynamic registry for MCP tools."""

    def __init__(self) -> None:
        self._tools: Dict[str, Callable] = {}
        self._schemas: Dict[str, Tool] = {}

    def register(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator to register a tool function."""
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._tools[name] = func
            self._schemas[name] = Tool(
                name=name,
                description=description,
                inputSchema=input_schema,
            )
            logger.info("Registered MCP tool: %s", name)
            return func
        return decorator

    def register_function(
        self, name: str, description: str, input_schema: Dict[str, Any], func: Callable
    ) -> None:
        """Programmatic tool registration (non-decorator)."""
        self._tools[name] = func
        self._schemas[name] = Tool(
            name=name,
            description=description,
            inputSchema=input_schema,
        )
        logger.info("Registered MCP tool: %s", name)

    async def call(self, name: str, arguments: Dict[str, Any]) -> Any:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}. Available: {list(self._tools.keys())}")
        func = self._tools[name]
        if asyncio.iscoroutinefunction(func):
            return await func(**arguments)
        return func(**arguments)

    def call_sync(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Synchronously call a registered tool (for sync-only contexts)."""
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}. Available: {list(self._tools.keys())}")
        func = self._tools[name]
        if asyncio.iscoroutinefunction(func):
            raise RuntimeError(f"Tool {name} is async and cannot be called synchronously")
        return func(**arguments)

    def list_tools(self) -> List[Tool]:
        return list(self._schemas.values())

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    @property
    def tool_count(self) -> int:
        return len(self._tools)


# Global registry instance
tool_registry = ToolRegistry()


def _resolve_static_dir(static_dir: str) -> Path:
    """Resolve static directory relative to repository root when needed."""
    path = Path(static_dir)
    if path.is_absolute():
        return path
    repo_root = Path(__file__).resolve().parents[2]
    return (repo_root / path).resolve()


def _display_label(sensor_id: str) -> str:
    return sensor_id.replace("_", " ").replace("-", " ").upper()


def _coerce_float(value: Any) -> Optional[float]:
    try:
        candidate = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(candidate):
        return None
    return candidate


def _coerce_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y", "on"}:
            return True
        if lowered in {"false", "0", "no", "n", "off"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return None


def _severity_from_score(score: Optional[float]) -> str:
    if score is None:
        return "UNKNOWN"
    if score >= 0.9:
        return "CRITICAL"
    if score >= 0.75:
        return "HIGH"
    if score >= 0.5:
        return "MEDIUM"
    return "LOW"


def _extract_anomaly_summary(
    scan_result: Any,
    latest_history_entry: Optional[Dict[str, Any]],
    fallback_threshold: float,
) -> Dict[str, Any]:
    scan_payload = scan_result if isinstance(scan_result, dict) else {}
    model_output = scan_payload.get("output", {})
    output_payload = model_output if isinstance(model_output, dict) else {}
    history_payload = latest_history_entry if isinstance(latest_history_entry, dict) else {}

    anomaly_score = _coerce_float(output_payload.get("anomaly_score"))
    if anomaly_score is None:
        anomaly_score = _coerce_float(scan_payload.get("anomaly_score"))
    if anomaly_score is None:
        anomaly_score = _coerce_float(history_payload.get("anomaly_score"))

    is_anomaly = _coerce_bool(output_payload.get("is_anomaly"))
    if is_anomaly is None:
        is_anomaly = _coerce_bool(scan_payload.get("is_anomaly"))
    if is_anomaly is None and anomaly_score is not None:
        is_anomaly = anomaly_score >= fallback_threshold
    if is_anomaly is None:
        is_anomaly = False

    confidence = _coerce_float(scan_payload.get("confidence"))
    if confidence is None:
        confidence = _coerce_float(output_payload.get("confidence"))
    if confidence is None:
        confidence = _coerce_float(history_payload.get("confidence"))

    return {
        "anomaly_score": anomaly_score,
        "is_anomaly": bool(is_anomaly),
        "severity": _severity_from_score(anomaly_score),
        "confidence": confidence,
    }


def _build_anomaly_id(
    model_id: str,
    scan_result: Any,
    latest_history_entry: Optional[Dict[str, Any]],
    summary: Dict[str, Any],
) -> str:
    """Build a stable ID for anomaly events so acknowledgments can be tracked."""
    reference_timestamp = ""
    if isinstance(latest_history_entry, dict):
        raw_ts = latest_history_entry.get("timestamp")
        if raw_ts is not None:
            reference_timestamp = str(raw_ts)

    if not reference_timestamp and isinstance(scan_result, dict):
        raw_scan_ts = scan_result.get("timestamp")
        if raw_scan_ts is not None:
            reference_timestamp = str(raw_scan_ts)
        else:
            raw_output = scan_result.get("output")
            if isinstance(raw_output, dict):
                raw_output_ts = raw_output.get("timestamp")
                if raw_output_ts is not None:
                    reference_timestamp = str(raw_output_ts)

    anomaly_score = _coerce_float(summary.get("anomaly_score"))
    score_label = "na" if anomaly_score is None else f"{anomaly_score:.4f}"
    severity = str(summary.get("severity", "UNKNOWN"))
    timestamp_label = reference_timestamp or "live"

    seed = f"{model_id}|{severity}|{score_label}|{timestamp_label}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
    return f"anom-{digest}"


def _build_sensor_catalog(config: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """Build a lightweight UI-safe catalog of configured sensors."""
    catalog: Dict[str, Dict[str, str]] = {}
    sensors_config = config.get("sensors", {})
    if not isinstance(sensors_config, dict):
        return catalog

    group_to_source = {
        "i2c_devices": "i2c",
        "spi_devices": "spi",
        "uart_devices": "uart",
    }

    for group_name, source in group_to_source.items():
        group = sensors_config.get(group_name, {})
        if not isinstance(group, dict):
            continue

        for sensor_id, raw_cfg in group.items():
            if not isinstance(sensor_id, str):
                continue
            sensor_cfg = raw_cfg if isinstance(raw_cfg, dict) else {}
            label = str(sensor_cfg.get("label") or _display_label(sensor_id))
            catalog[sensor_id] = {
                "id": sensor_id,
                "label": label,
                "source": source,
            }

    adc_channels = sensors_config.get("adc_channels", {})
    if isinstance(adc_channels, dict):
        for channel_id, raw_cfg in adc_channels.items():
            if not isinstance(channel_id, str):
                continue
            channel_cfg = raw_cfg if isinstance(raw_cfg, dict) else {}
            label = str(channel_cfg.get("label") or _display_label(channel_id))
            catalog[f"ads1263:{channel_id}"] = {
                "id": f"ads1263:{channel_id}",
                "label": label,
                "source": "adc_channel",
            }

    return catalog


def _sanitize_ui_config(
    ui_config: Dict[str, Any],
    ui_static_available: bool,
    full_config: Dict[str, Any],
) -> Dict[str, Any]:
    """Return UI configuration safe for frontend consumption."""
    panels_raw = ui_config.get("panels", {})
    panels: Dict[str, Dict[str, Any]] = panels_raw if isinstance(panels_raw, dict) else {}

    panel_order_raw = ui_config.get("panel_order", [])
    panel_order: List[str] = []
    if isinstance(panel_order_raw, list):
        panel_order = [str(key) for key in panel_order_raw if str(key) in panels]
    if not panel_order:
        panel_order = list(panels.keys())

    sensor_catalog = _build_sensor_catalog(full_config)
    for panel in panels.values():
        if not isinstance(panel, dict):
            continue
        sensors = panel.get("sensors", [])
        if not isinstance(sensors, list):
            continue
        for raw_sensor_id in sensors:
            sensor_id = str(raw_sensor_id)
            if sensor_id not in sensor_catalog:
                sensor_catalog[sensor_id] = {
                    "id": sensor_id,
                    "label": _display_label(sensor_id),
                    "source": "unknown",
                }

    return {
        "project_name": str(full_config.get("project_name", "TRICORDER")),
        "version": str(full_config.get("version", "1.0.0")),
        "enabled": bool(ui_config.get("enabled", False)) and ui_static_available,
        "theme": str(ui_config.get("theme", "classic")),
        "debug": bool(ui_config.get("debug", False)),
        "poll_interval_ms": int(ui_config.get("poll_interval_ms", 1000)),
        "ws_heartbeat_s": int(ui_config.get("ws_heartbeat_s", 30)),
        "ws_path": str(ui_config.get("ws_path", DEFAULT_UI_WS_PATH)),
        "anomaly_ws_path": str(ui_config.get("anomaly_ws_path", DEFAULT_UI_ANOMALY_WS_PATH)),
        "anomaly_poll_interval_ms": int(ui_config.get("anomaly_poll_interval_ms", 2000)),
        "anomaly_model_id": str(ui_config.get("anomaly_model_id", "anomaly_detector")),
        "anomaly_history_limit": int(ui_config.get("anomaly_history_limit", 1)),
        "anomaly_ack_enabled": bool(ui_config.get("anomaly_ack_enabled", True)),
        "anomaly_ack_path": str(ui_config.get("anomaly_ack_path", DEFAULT_UI_ANOMALY_ACK_PATH)),
        "anomaly_ack_history_limit": int(ui_config.get("anomaly_ack_history_limit", 500)),
        "anomaly_alert_threshold": float(ui_config.get("anomaly_alert_threshold", 0.75)),
        "agent_enabled": bool(ui_config.get("agent_enabled", True)),
        "agent_chat_path": str(ui_config.get("agent_chat_path", DEFAULT_UI_AGENT_CHAT_PATH)),
        "reconnect_initial_ms": int(ui_config.get("reconnect_initial_ms", 1500)),
        "reconnect_max_ms": int(ui_config.get("reconnect_max_ms", 10000)),
        "panel_order": panel_order,
        "panels": panels,
        "sensor_catalog": sensor_catalog,
    }


def create_app(
    config: Optional[Dict[str, Any]] = None,
    registry: Optional[ToolRegistry] = None,
) -> FastAPI:
    """
    Create FastAPI MCP server app.

    Args:
        config: MCP server configuration dict
        registry: Optional tool registry (defaults to global)
    """
    config = config or {}
    server_config = config.get("mcp_server", config)
    ui_config = config.get("ui", {})
    if not isinstance(ui_config, dict):
        ui_config = {}

    reg = registry or tool_registry

    app = FastAPI(
        title=config.get("project_name", config.get("title", "Tricorder MCP Server")),
        version=config.get("version", "1.0.0"),
    )

    auth_enabled = server_config.get("auth_enabled", False)
    api_key = server_config.get("api_key")

    ui_enabled = bool(ui_config.get("enabled", False))
    ui_static_dir = _resolve_static_dir(ui_config.get("static_dir", "src/ui/static"))
    ui_static_available = ui_static_dir.exists()
    if ui_enabled and not ui_static_available:
        logger.warning("UI static directory does not exist: %s", ui_static_dir)

    ui_public_config = _sanitize_ui_config(ui_config, ui_static_available, config)
    ui_poll_interval_s = max(int(ui_public_config["poll_interval_ms"]), 100) / 1000.0
    ui_ws_path = str(ui_public_config.get("ws_path", DEFAULT_UI_WS_PATH))
    if not ui_ws_path.startswith("/"):
        logger.warning("Invalid ui.ws_path=%s, falling back to %s", ui_ws_path, DEFAULT_UI_WS_PATH)
        ui_ws_path = DEFAULT_UI_WS_PATH

    ui_anomaly_poll_interval_s = max(
        int(ui_public_config.get("anomaly_poll_interval_ms", 2000)),
        250,
    ) / 1000.0
    ui_anomaly_ws_path = str(
        ui_public_config.get("anomaly_ws_path", DEFAULT_UI_ANOMALY_WS_PATH),
    )
    if not ui_anomaly_ws_path.startswith("/"):
        logger.warning(
            "Invalid ui.anomaly_ws_path=%s, falling back to %s",
            ui_anomaly_ws_path,
            DEFAULT_UI_ANOMALY_WS_PATH,
        )
        ui_anomaly_ws_path = DEFAULT_UI_ANOMALY_WS_PATH

    agent_enabled = bool(ui_public_config.get("agent_enabled", True))
    agent_chat_path = str(
        ui_public_config.get("agent_chat_path", DEFAULT_UI_AGENT_CHAT_PATH),
    )
    if not agent_chat_path.startswith("/"):
        logger.warning(
            "Invalid ui.agent_chat_path=%s, falling back to %s",
            agent_chat_path,
            DEFAULT_UI_AGENT_CHAT_PATH,
        )
        agent_chat_path = DEFAULT_UI_AGENT_CHAT_PATH

    anomaly_model_id = str(ui_public_config.get("anomaly_model_id", "anomaly_detector"))
    anomaly_history_limit = max(int(ui_public_config.get("anomaly_history_limit", 1)), 1)
    anomaly_ack_enabled = bool(ui_public_config.get("anomaly_ack_enabled", True))
    anomaly_ack_path = str(
        ui_public_config.get("anomaly_ack_path", DEFAULT_UI_ANOMALY_ACK_PATH),
    )
    if not anomaly_ack_path.startswith("/"):
        logger.warning(
            "Invalid ui.anomaly_ack_path=%s, falling back to %s",
            anomaly_ack_path,
            DEFAULT_UI_ANOMALY_ACK_PATH,
        )
        anomaly_ack_path = DEFAULT_UI_ANOMALY_ACK_PATH

    anomaly_ack_history_limit = max(
        int(ui_public_config.get("anomaly_ack_history_limit", 500)),
        1,
    )
    anomaly_alert_threshold = float(ui_public_config.get("anomaly_alert_threshold", 0.75))

    acknowledged_anomalies: Dict[str, Dict[str, Any]] = {}
    acknowledged_order: List[str] = []

    def _upsert_anomaly_ack(anomaly_id: str, record: Dict[str, Any]) -> None:
        if anomaly_id not in acknowledged_anomalies:
            acknowledged_order.append(anomaly_id)
        acknowledged_anomalies[anomaly_id] = record

        while len(acknowledged_order) > anomaly_ack_history_limit:
            oldest = acknowledged_order.pop(0)
            acknowledged_anomalies.pop(oldest, None)

    agent_runner: Optional[Any] = None
    if agent_enabled:
        try:
            from agents.langgraph_agent import TricorderAgent

            agent_config = config.get("agent", {})
            if not isinstance(agent_config, dict):
                agent_config = {}

            def _agent_tool_caller(name: str, args: Dict[str, Any]) -> Any:
                return reg.call_sync(name, args)

            agent_runner = TricorderAgent(config=agent_config, tool_caller=_agent_tool_caller)
            agent_runner.build_graph()
        except Exception as e:
            logger.warning("Agent chat disabled: failed to initialize agent (%s)", e)

    @app.middleware("http")
    async def auth_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Any]],
    ) -> Any:
        if auth_enabled and request.url.path not in AUTH_PUBLIC_PATHS:
            if not api_key:
                logger.error("Authentication enabled but no API key configured")
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Authentication is enabled but not configured"},
                )

            token = request.headers.get("Authorization", "").replace("Bearer ", "")
            if not hmac.compare_digest(token, api_key):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or missing API key"},
                )
        return await call_next(request)

    @app.get("/health")
    async def health() -> Dict[str, Any]:
        return {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tools_registered": reg.tool_count,
        }

    if ui_enabled and ui_static_available:
        @app.get("/", include_in_schema=False)
        async def root_redirect() -> RedirectResponse:
            return RedirectResponse(url="/ui/index.html")

    @app.get("/ui/config.json")
    async def get_ui_config() -> Dict[str, Any]:
        return ui_public_config

    @app.get("/tools")
    async def get_tools() -> List[Dict[str, Any]]:
        return [t.model_dump() for t in reg.list_tools()]

    @app.post("/tools/call")
    async def call_tool(request: ToolCallRequest) -> ToolCallResponse:
        try:
            result = await reg.call(request.name, request.arguments)
            return ToolCallResponse(content=result, isError=False)
        except KeyError:
            raise HTTPException(status_code=404, detail="Tool not found")
        except TypeError:
            raise HTTPException(status_code=400, detail="Invalid tool arguments")
        except Exception as e:
            logger.error("Tool call %s failed: %s", request.name, e, exc_info=True)
            return ToolCallResponse(
                content={"error": "Tool call failed. Check logs for details."},
                isError=True,
            )

    async def _build_anomaly_payload() -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model_id": anomaly_model_id,
        }
        scan_result: Any = {}
        history_entries: List[Dict[str, Any]] = []
        latest_history_entry: Optional[Dict[str, Any]] = None

        if reg.has_tool("run_anomaly_scan"):
            try:
                scan_result = await reg.call(
                    "run_anomaly_scan",
                    {"model_id": anomaly_model_id},
                )
            except Exception as e:
                logger.warning("Anomaly scan call failed: %s", e)
                payload["scan_error"] = "Anomaly scan unavailable"

        if reg.has_tool("get_anomaly_history"):
            try:
                history_result = await reg.call(
                    "get_anomaly_history",
                    {
                        "model_id": anomaly_model_id,
                        "limit": anomaly_history_limit,
                    },
                )
                if isinstance(history_result, dict):
                    entries = history_result.get("entries", [])
                    if isinstance(entries, list):
                        history_entries = [
                            entry for entry in entries if isinstance(entry, dict)
                        ]
                        if history_entries:
                            latest_history_entry = history_entries[-1]
            except Exception as e:
                logger.warning("Anomaly history call failed: %s", e)
                payload["history_error"] = "Anomaly history unavailable"

        summary = _extract_anomaly_summary(
            scan_result=scan_result,
            latest_history_entry=latest_history_entry,
            fallback_threshold=anomaly_alert_threshold,
        )
        payload.update(summary)

        anomaly_id = _build_anomaly_id(
            model_id=anomaly_model_id,
            scan_result=scan_result,
            latest_history_entry=latest_history_entry,
            summary=summary,
        )
        payload["anomaly_id"] = anomaly_id

        ack_record = acknowledged_anomalies.get(anomaly_id)
        payload["acknowledged"] = ack_record is not None
        if ack_record is not None:
            payload["acknowledgment"] = ack_record

        payload["history"] = history_entries
        return payload

    async def _authorize_websocket(websocket: WebSocket) -> bool:
        if auth_enabled:
            if not api_key:
                logger.error("Authentication enabled but no API key configured for websocket")
                await websocket.close(code=1008)
                return False

            token = websocket.query_params.get("token") or websocket.query_params.get("api_key")
            if not token or not hmac.compare_digest(token, api_key):
                await websocket.close(code=1008)
                return False
        return True

    @app.post(agent_chat_path)
    async def ui_agent_chat(request: AgentChatRequest) -> Dict[str, Any]:
        if not agent_enabled:
            raise HTTPException(status_code=404, detail="Agent chat is disabled")
        if agent_runner is None:
            raise HTTPException(status_code=503, detail="Agent runner is unavailable")

        sensor_snapshot: Dict[str, Any] = {}
        affected_sensors: List[str] = []
        if request.include_sensor_context and reg.has_tool("read_all_sensors"):
            try:
                snapshot = await reg.call("read_all_sensors", {})
                if isinstance(snapshot, dict):
                    sensor_snapshot = snapshot
                    affected_sensors = [str(sensor_id) for sensor_id in snapshot.keys()]
            except Exception as e:
                logger.warning("Failed to collect sensor context for agent chat: %s", e)

        anomaly_payload = await _build_anomaly_payload()
        anomaly_score = _coerce_float(anomaly_payload.get("anomaly_score"))
        if anomaly_score is None:
            anomaly_score = 0.0

        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_query": request.query,
            "anomaly_score": anomaly_score,
            "affected_sensors": affected_sensors[:8],
            "context": {
                "sensor_snapshot": sensor_snapshot,
                "anomaly": anomaly_payload,
            },
        }

        try:
            agent_result = agent_runner.run(event)
        except Exception as e:
            logger.error("Agent chat failed: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail="Agent execution failed")

        result_payload = agent_result if isinstance(agent_result, dict) else {}
        report = str(result_payload.get("report") or "No report generated.")

        return {
            "query": request.query,
            "reply": f"QUERY: {request.query}\n\n{report}",
            "report": report,
            "severity": str(result_payload.get("severity") or "UNKNOWN"),
            "needs_human_approval": bool(result_payload.get("needs_human_approval", False)),
            "messages": result_payload.get("messages", []),
            "tool_results": result_payload.get("tool_results", []),
            "context": {
                "anomaly": anomaly_payload,
                "sensors": affected_sensors,
            },
        }

    @app.post(anomaly_ack_path)
    async def ui_anomaly_ack(request: AnomalyAcknowledgeRequest) -> Dict[str, Any]:
        if not anomaly_ack_enabled:
            raise HTTPException(status_code=404, detail="Anomaly acknowledgment is disabled")

        anomaly_id = request.anomaly_id.strip()
        if not anomaly_id:
            raise HTTPException(status_code=400, detail="anomaly_id must not be blank")

        record = {
            "anomaly_id": anomaly_id,
            "acknowledged_at": datetime.now(timezone.utc).isoformat(),
            "acknowledged_by": request.acknowledged_by.strip() or "ui",
            "note": (request.note or "").strip(),
        }
        _upsert_anomaly_ack(anomaly_id, record)

        return {
            "ok": True,
            "acknowledgment": record,
            "count": len(acknowledged_anomalies),
        }

    async def stream_sensor_data(websocket: WebSocket) -> None:
        if not await _authorize_websocket(websocket):
            return

        await websocket.accept()
        logger.info("Sensor stream client connected")
        try:
            while True:
                payload: Dict[str, Any] = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "readings": {},
                }
                if reg.has_tool("read_all_sensors"):
                    try:
                        payload["readings"] = await reg.call("read_all_sensors", {})
                    except Exception as e:
                        logger.warning("Failed to fetch sensor readings for websocket: %s", e)
                        payload["error"] = "Sensor readings unavailable"

                await websocket.send_json(payload)
                await asyncio.sleep(ui_poll_interval_s)
        except WebSocketDisconnect:
            logger.info("Sensor stream client disconnected")
        except Exception as e:
            logger.error("Sensor websocket failed: %s", e, exc_info=True)
            await websocket.close(code=1011)

    async def stream_anomaly_data(websocket: WebSocket) -> None:
        if not await _authorize_websocket(websocket):
            return

        await websocket.accept()
        logger.info("Anomaly stream client connected")
        try:
            while True:
                payload = await _build_anomaly_payload()
                await websocket.send_json(payload)
                await asyncio.sleep(ui_anomaly_poll_interval_s)
        except WebSocketDisconnect:
            logger.info("Anomaly stream client disconnected")
        except Exception as e:
            logger.error("Anomaly websocket failed: %s", e, exc_info=True)
            await websocket.close(code=1011)

    registered_ws_paths: set[str] = set()

    def _register_ws_route(path: str, handler: Callable[[WebSocket], Awaitable[None]]) -> None:
        if path in registered_ws_paths:
            return
        app.add_api_websocket_route(path, handler)
        registered_ws_paths.add(path)

    _register_ws_route(DEFAULT_UI_WS_PATH, stream_sensor_data)
    _register_ws_route(ui_ws_path, stream_sensor_data)
    _register_ws_route(DEFAULT_UI_ANOMALY_WS_PATH, stream_anomaly_data)
    _register_ws_route(ui_anomaly_ws_path, stream_anomaly_data)

    if ui_enabled and ui_static_available:
        app.mount("/ui", StaticFiles(directory=str(ui_static_dir), html=True), name="ui")

    return app


def main() -> None:
    """Entry point for running MCP server standalone."""
    import uvicorn
    from utils.config import load_config

    config = load_config()
    app = create_app(config=config.model_dump())
    uvicorn.run(
        app,
        host=config.mcp_server.host,
        port=config.mcp_server.port,
    )


if __name__ == "__main__":
    main()
