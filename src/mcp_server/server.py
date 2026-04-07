"""MCP Server for Tricorder Neural Platform.

Exposes sensor tools via FastAPI with dynamic tool registry.
All configuration loaded from TricorderConfig — no hardcoded values.
"""

from typing import Any, Awaitable, Callable, Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime, timezone
import asyncio
import hmac
import logging
import math
import random
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from mcp_server.anomaly_helpers import (
    build_anomaly_id,
    coerce_float,
    extract_anomaly_summary,
)
from mcp_server.tools.anomaly_tools import register_anomaly_tools
from mcp_server.tools.sensor_tools import register_sensor_tools
from mcp_server.ui_helpers import (
    build_query_intent_note,
    sanitize_ui_config,
    DEFAULT_UI_AGENT_CHAT_PATH,
    DEFAULT_UI_ANOMALY_ACK_PATH,
    DEFAULT_UI_ANOMALY_WS_PATH,
    DEFAULT_UI_WS_PATH,
)
from sensors.base import BaseSensor, SensorReading, SensorStatus
from sensors.manager import SensorManager
from utils.constants import (
    AGENT_CHAT_QUERY_MAX_LENGTH,
    SENSOR_GROUPS,
)

logger = logging.getLogger(__name__)


class MCPServerError(Exception):
    """Base exception for MCP server errors."""
    pass


class ToolExecutionError(MCPServerError):
    """Raised when a tool call fails during execution."""
    pass


class AuthenticationError(MCPServerError):
    """Raised when an authentication check fails."""
    pass


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

    query: str = Field(..., min_length=1, max_length=AGENT_CHAT_QUERY_MAX_LENGTH)
    include_sensor_context: bool = Field(default=True)
    operator_id: Optional[str] = Field(
        default=None, max_length=64,
        description="Explicit operator identity. If absent, derived from auth context.",
    )


class AnomalyAcknowledgeRequest(BaseModel):
    """Request payload for anomaly acknowledgment endpoint."""

    anomaly_id: str = Field(..., min_length=1, max_length=128)
    acknowledged_by: str = Field(default="ui", min_length=1, max_length=64)
    note: Optional[str] = Field(default=None, max_length=256)
    operator_source: Optional[str] = Field(
        default=None, max_length=32,
        description="How operator identity was determined (auto-populated if not set).",
    )


@dataclass
class OperatorContext:
    """Lightweight identity context for the current request operator."""

    operator_id: str = "anonymous"
    source: str = "anonymous"


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


def _resolve_static_dir(static_dir: str) -> Path:
    """Resolve static directory relative to repository root when needed."""
    path = Path(static_dir)
    if path.is_absolute():
        return path
    repo_root = Path(__file__).resolve().parents[2]
    return (repo_root / path).resolve()


def _iter_enabled_sensor_ids(sensors_config: Dict[str, Any]) -> List[str]:
    sensor_ids: List[str] = []
    for group_name in SENSOR_GROUPS:
        group = sensors_config.get(group_name, {})
        if not isinstance(group, dict):
            continue
        for sensor_id, raw_cfg in group.items():
            if not isinstance(sensor_id, str):
                continue
            sensor_cfg = raw_cfg if isinstance(raw_cfg, dict) else {}
            if sensor_cfg.get("enabled", True):
                sensor_ids.append(sensor_id)
    return sensor_ids


# ---------------------------------------------------------------------------
# Simulation registry — each sensor type registers a factory function that
# produces realistic-looking fake data for development / test environments.
# ---------------------------------------------------------------------------
_SIMULATION_REGISTRY: Dict[str, Callable[..., Dict[str, Any]]] = {}


def _register_simulation(sensor_pattern: str) -> Callable:
    """Decorator to register a simulated-value factory for *sensor_pattern*."""
    def decorator(func: Callable[..., Dict[str, Any]]) -> Callable[..., Dict[str, Any]]:
        _SIMULATION_REGISTRY[sensor_pattern] = func
        return func
    return decorator


@_register_simulation("bme680")
def _sim_bme680(_sensors_config: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "temperature_c": round(random.uniform(20.0, 26.0), 2),
        "humidity_rh": round(random.uniform(35.0, 60.0), 2),
        "pressure_hpa": round(random.uniform(1005.0, 1022.0), 2),
        "gas_resistance_ohm": round(random.uniform(12000.0, 42000.0), 2),
    }


@_register_simulation("mlx90640")
def _sim_mlx90640(_sensors_config: Dict[str, Any]) -> Dict[str, Any]:
    thermal_frame = [round(random.uniform(24.0, 34.0), 2) for _ in range(24)]
    return {
        "min_temp_c": min(thermal_frame),
        "avg_temp_c": round(sum(thermal_frame) / len(thermal_frame), 2),
        "max_temp_c": max(thermal_frame),
        "thermal_frame": thermal_frame,
    }


@_register_simulation("as7265x")
def _sim_as7265x(_sensors_config: Dict[str, Any]) -> Dict[str, Any]:
    wavelengths = (
        "410nm", "435nm", "460nm", "485nm", "510nm", "535nm",
        "560nm", "585nm", "610nm", "645nm", "680nm", "705nm",
    )
    return {
        "spectral_channels": {
            name: round(random.uniform(0.05, 1.0), 3) for name in wavelengths
        }
    }


@_register_simulation("ads1263")
def _sim_ads1263(sensors_config: Dict[str, Any]) -> Dict[str, Any]:
    adc_channels = sensors_config.get("adc_channels", {})
    if isinstance(adc_channels, dict) and adc_channels:
        channel_values = {
            str(channel_id): round(random.uniform(0.02, 2.8), 3)
            for channel_id in adc_channels.keys()
        }
    else:
        channel_values = {
            "ch0": round(random.uniform(0.02, 2.8), 3),
            "ch1": round(random.uniform(0.02, 2.8), 3),
        }
    return {"channels": channel_values}


@_register_simulation("hlk_ld2410")
def _sim_hlk_ld2410(_sensors_config: Dict[str, Any]) -> Dict[str, Any]:
    moving_distance = random.randint(50, 450)
    still_distance = random.randint(30, 220)
    detection_distance = max(moving_distance, still_distance)
    return {
        "target_state": random.choice(["moving", "still", "none"]),
        "moving_target_energy": random.randint(0, 100),
        "stationary_target_energy": random.randint(0, 100),
        "moving_target_distance_cm": moving_distance,
        "stationary_target_distance_cm": still_distance,
        "detection_distance_cm": detection_distance,
    }


@_register_simulation("tfmini")
def _sim_tfmini(_sensors_config: Dict[str, Any]) -> Dict[str, Any]:
    valid = random.random() > 0.1
    return {
        "distance_cm": random.randint(35, 500) if valid else None,
        "signal_strength": random.randint(30, 200) if valid else None,
        "temperature_c": round(random.uniform(25.0, 37.0), 2) if valid else None,
        "max_range_cm": 1200,
        "valid": valid,
    }


@_register_simulation("max30102")
def _sim_max30102(_sensors_config: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "heart_rate_bpm": round(random.uniform(58.0, 92.0), 1),
        "spo2_percent": round(random.uniform(95.0, 100.0), 1),
        "ir_avg": round(random.uniform(32000.0, 76000.0), 2),
    }


def _build_simulated_sensor_value(sensor_id: str, sensors_config: Dict[str, Any]) -> Dict[str, Any]:
    sensor_key = sensor_id.lower()
    for pattern, factory in _SIMULATION_REGISTRY.items():
        if pattern in sensor_key:
            return factory(sensors_config)
    return {"value": round(random.uniform(0.0, 1.0), 4)}


class _SimulatedSensor(BaseSensor):
    """Development-only simulated sensor used when hardware is unavailable."""

    def __init__(self, sensor_id: str, sensors_config: Dict[str, Any]) -> None:
        super().__init__(sensor_id=sensor_id, adapter=None, config={"simulated": True})
        self._sensors_config = sensors_config

    def _do_initialize(self) -> bool:
        return True

    def _do_read(self) -> SensorReading:
        return SensorReading(
            sensor_id=self.sensor_id,
            timestamp=datetime.now(timezone.utc),
            value=_build_simulated_sensor_value(self.sensor_id, self._sensors_config),
            confidence=0.92,
            metadata={"simulated": True},
        )

    def calibrate(self, **kwargs: Any) -> bool:
        self.status = SensorStatus.CALIBRATING
        self.status = SensorStatus.READY
        return True

    def get_diagnostics(self) -> Dict[str, Any]:
        diagnostics = super().get_diagnostics()
        diagnostics["simulated"] = True
        return diagnostics


def _bootstrap_default_tools(registry: ToolRegistry, config: Dict[str, Any]) -> SensorManager:
    """Populate the default registry with sensor and anomaly tools."""
    sensor_manager = SensorManager()
    sensors_config = config.get("sensors", {})
    sensors_dict = sensors_config if isinstance(sensors_config, dict) else {}
    environment = str(config.get("environment", "development")).strip().lower()
    use_simulated_sensors = environment in {"development", "dev", "local", "test"}

    if use_simulated_sensors:
        configured_sensor_ids = _iter_enabled_sensor_ids(sensors_dict)
        for sensor_id in configured_sensor_ids:
            sensor_manager.register_sensor(sensor_id, _SimulatedSensor(sensor_id, sensors_dict))
        init_results = sensor_manager.initialize_all()
        ready_count = sum(1 for initialized in init_results.values() if initialized)
        logger.info(
            "Initialized %d/%d development simulated sensors",
            ready_count,
            len(init_results),
        )

    register_sensor_tools(registry, sensor_manager)
    register_anomaly_tools(registry)
    logger.info("Default MCP tool bootstrap complete: %d tools", registry.tool_count)
    return sensor_manager


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

    reg = registry if registry is not None else ToolRegistry()
    sensor_manager: Optional[SensorManager] = None
    if registry is None:
        sensor_manager = _bootstrap_default_tools(reg, config)

    app = FastAPI(
        title=config.get("project_name", config.get("title", "Tricorder MCP Server")),
        version=config.get("version", "1.0.0"),
    )
    app.state.tool_registry = reg
    if sensor_manager is not None:
        app.state.sensor_manager = sensor_manager

    @app.exception_handler(404)
    async def _not_found_handler(request: Request, _exc: HTTPException) -> Any:
        if request.url.path.startswith("/ui/"):
            return HTMLResponse(
                content="<html><body><h1>404 Not Found</h1>"
                "<p>The requested resource could not be found.</p>"
                "<p><a href='/ui/'>Return to Tricorder</a></p></body></html>",
                status_code=404,
            )
        detail = _exc.detail if _exc.detail else "Not Found"
        return JSONResponse(content={"detail": detail}, status_code=404)

    auth_enabled = server_config.get("auth_enabled", False)
    api_key = server_config.get("api_key")

    ui_enabled = bool(ui_config.get("enabled", False))
    ui_static_dir = _resolve_static_dir(ui_config.get("static_dir", "src/ui/static"))
    ui_static_available = ui_static_dir.exists()
    if ui_enabled and not ui_static_available:
        logger.warning("UI static directory does not exist: %s", ui_static_dir)

    ui_public_config = sanitize_ui_config(ui_config, ui_static_available, config)
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
    anomaly_history_path = str(
        ui_public_config.get("anomaly_history_path", "/ui/anomalies/history"),
    )
    if not anomaly_history_path.startswith("/"):
        anomaly_history_path = "/ui/anomalies/history"
    anomaly_history_page_size = max(
        int(ui_public_config.get("anomaly_history_page_size", 50)), 10,
    )
    anomaly_alert_threshold = float(ui_public_config.get("anomaly_alert_threshold", 0.75))
    # Read severity thresholds from agent config for consistent labeling
    _agent_cfg = config.get("agent", {})
    severity_thresholds: Optional[Dict[str, float]] = (
        _agent_cfg.get("severity_thresholds") if isinstance(_agent_cfg, dict) else None
    )

    from mcp_server.ack_store import create_ack_store

    anomaly_ack_db_path = str(ui_public_config.get("anomaly_ack_db_path", ""))
    ack_store = create_ack_store(
        db_path=anomaly_ack_db_path or None,
        max_records=anomaly_ack_history_limit,
    )
    app.state.ack_store = ack_store

    # Operator identity mapping
    raw_op_map = server_config.get("operator_map", {})
    operator_map: Dict[str, str] = (
        {str(k): str(v) for k, v in raw_op_map.items()}
        if isinstance(raw_op_map, dict) else {}
    )

    agent_runner: Optional[Any] = None
    if agent_enabled:
        try:
            from agents.langgraph_agent import TricorderAgent

            agent_config = config.get("agent", {})
            if not isinstance(agent_config, dict):
                agent_config = {}

            def _agent_tool_caller(name: str, args: Dict[str, Any]) -> Any:
                return reg.call_sync(name, args)

            # Optionally wire up LLM client for report synthesis
            llm_client = None
            feature_flags = config.get("feature_flags", {})
            if isinstance(feature_flags, dict) and feature_flags.get("llm_enabled", False):
                try:
                    from agents.llm_client import OllamaClient

                    llm_client = OllamaClient(
                        endpoint=agent_config.get("llm_endpoint", "http://localhost:11434"),
                        model=agent_config.get("model_name", "qwen2.5:3b"),
                        timeout_s=float(agent_config.get("llm_timeout_s", 30.0)),
                    )
                except Exception as llm_err:
                    logger.warning("LLM client init failed: %s", llm_err)

            agent_runner = TricorderAgent(
                config=agent_config,
                tool_caller=_agent_tool_caller,
                llm_client=llm_client,
            )
            agent_runner.build_graph()
        except Exception as e:
            logger.warning("Agent chat disabled: failed to initialize agent (%s)", e)

    @app.middleware("http")
    async def auth_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Any]],
    ) -> Any:
        # Default anonymous operator context
        request.state.operator = OperatorContext()

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

            # Token is valid — derive operator identity
            if token in operator_map:
                request.state.operator = OperatorContext(
                    operator_id=operator_map[token],
                    source="bearer_token",
                )
            else:
                request.state.operator = OperatorContext(
                    operator_id=f"token:{token[:8]}",
                    source="api_key",
                )
        elif not auth_enabled:
            # Auth disabled — check if token was sent voluntarily
            token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
            if token and operator_map and token in operator_map:
                request.state.operator = OperatorContext(
                    operator_id=operator_map[token],
                    source="bearer_token",
                )

        logger.debug(
            "Operator resolved: id=%s, source=%s",
            request.state.operator.operator_id,
            request.state.operator.source,
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
        logger.debug("call_tool entry: name=%s", request.name)
        try:
            result = await reg.call(request.name, request.arguments)
            logger.debug("call_tool exit: name=%s success=True", request.name)
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

        summary = extract_anomaly_summary(
            scan_result=scan_result,
            latest_history_entry=latest_history_entry,
            fallback_threshold=anomaly_alert_threshold,
            severity_thresholds=severity_thresholds,
        )
        payload.update(summary)

        anomaly_id = build_anomaly_id(
            model_id=anomaly_model_id,
            scan_result=scan_result,
            latest_history_entry=latest_history_entry,
            summary=summary,
        )
        payload["anomaly_id"] = anomaly_id

        ack_record = ack_store.get(anomaly_id)
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
    async def ui_agent_chat(
        body: AgentChatRequest, request: Request,
    ) -> Dict[str, Any]:
        logger.debug("ui_agent_chat entry: query=%r", body.query[:80])
        if not agent_enabled:
            raise HTTPException(status_code=404, detail="Agent chat is disabled")
        if agent_runner is None:
            raise HTTPException(status_code=503, detail="Agent runner is unavailable")

        # Resolve operator identity
        operator: OperatorContext = getattr(
            request.state, "operator", OperatorContext(),
        )
        effective_operator = body.operator_id or operator.operator_id

        sensor_snapshot: Dict[str, Any] = {}
        affected_sensors: List[str] = []
        if body.include_sensor_context and reg.has_tool("read_all_sensors"):
            try:
                snapshot = await reg.call("read_all_sensors", {})
                if isinstance(snapshot, dict):
                    sensor_snapshot = snapshot
                    affected_sensors = [str(sensor_id) for sensor_id in snapshot.keys()]
            except Exception as e:
                logger.warning("Failed to collect sensor context for agent chat: %s", e)

        anomaly_payload = await _build_anomaly_payload()
        anomaly_score = coerce_float(anomaly_payload.get("anomaly_score"))
        if anomaly_score is None:
            anomaly_score = 0.0

        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_query": body.query,
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
        query_note = build_query_intent_note(body.query, sensor_snapshot)
        reply_sections = [f"QUERY: {body.query}"]
        if query_note:
            reply_sections.append(query_note)
        reply_sections.append(report)
        reply_text = "\n\n".join(reply_sections)

        return {
            "query": body.query,
            "reply": reply_text,
            "report": report,
            "severity": str(result_payload.get("severity") or "UNKNOWN"),
            "needs_human_approval": bool(result_payload.get("needs_human_approval", False)),
            "messages": result_payload.get("messages", []),
            "tool_results": result_payload.get("tool_results", []),
            "context": {
                "anomaly": anomaly_payload,
                "sensors": affected_sensors,
                "operator_id": effective_operator,
            },
        }

    @app.get(anomaly_ack_path)
    async def ui_anomaly_ack_info() -> Dict[str, Any]:
        """Describe the anomaly acknowledgment endpoint."""
        return {
            "endpoint": anomaly_ack_path,
            "method": "POST",
            "note": "POST with anomaly_id to acknowledge an anomaly.",
        }

    @app.post(anomaly_ack_path)
    async def ui_anomaly_ack(
        body: AnomalyAcknowledgeRequest, request: Request,
    ) -> Dict[str, Any]:
        if not anomaly_ack_enabled:
            raise HTTPException(status_code=404, detail="Anomaly acknowledgment is disabled")

        anomaly_id = body.anomaly_id.strip()
        if not anomaly_id:
            raise HTTPException(status_code=400, detail="anomaly_id must not be blank")

        # Resolve operator identity
        operator: OperatorContext = getattr(
            request.state, "operator", OperatorContext(),
        )
        acknowledged_by = body.acknowledged_by.strip() or "ui"
        if acknowledged_by == "ui" and operator.operator_id != "anonymous":
            acknowledged_by = operator.operator_id
        operator_source = body.operator_source or operator.source

        record = {
            "anomaly_id": anomaly_id,
            "acknowledged_at": datetime.now(timezone.utc).isoformat(),
            "acknowledged_by": acknowledged_by,
            "note": (body.note or "").strip(),
            "operator_source": operator_source,
        }
        ack_store.upsert(anomaly_id, record)
        logger.info(
            "Anomaly %s acknowledged by %s (source=%s)",
            anomaly_id, acknowledged_by, operator_source,
        )

        return {
            "ok": True,
            "acknowledgment": record,
            "count": ack_store.count(),
        }

    @app.get(anomaly_history_path)
    async def ui_anomaly_history(
        page: int = 1,
        page_size: int = 0,
        acknowledged_by: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return paginated anomaly acknowledgment history."""
        effective_page_size = page_size if page_size > 0 else anomaly_history_page_size
        effective_page_size = max(1, min(effective_page_size, 500))
        effective_page = max(1, page)
        offset = (effective_page - 1) * effective_page_size

        filters: Dict[str, str] = {}
        if acknowledged_by:
            filters["acknowledged_by"] = acknowledged_by
        if date_from:
            filters["date_from"] = date_from
        if date_to:
            filters["date_to"] = date_to

        items = ack_store.list_acks(
            limit=effective_page_size, offset=offset, filters=filters or None,
        )
        total = ack_store.count(filters=filters or None)
        total_pages = max(1, math.ceil(total / effective_page_size))

        return {
            "items": items,
            "page": effective_page,
            "page_size": effective_page_size,
            "total": total,
            "total_pages": total_pages,
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
