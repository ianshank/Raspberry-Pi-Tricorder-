"""Pure helper functions for UI configuration and display.

Extracted from server.py for testability and separation of concerns.
All functions are stateless and have no server dependencies.
"""

from typing import Any, Dict, List

from utils.constants import DEFAULT_SEVERITY_THRESHOLDS, SENSOR_GROUPS

# Default websocket / endpoint paths (also defined in server.py for route setup)
DEFAULT_UI_WS_PATH = "/ws/sensors"
DEFAULT_UI_ANOMALY_WS_PATH = "/ws/anomalies"
DEFAULT_UI_ANOMALY_ACK_PATH = "/ui/anomalies/ack"
DEFAULT_UI_AGENT_CHAT_PATH = "/ui/agent/chat"


def display_label(sensor_id: str) -> str:
    """Convert a sensor_id like ``bme680_env`` to ``BME680 ENV``."""
    return sensor_id.replace("_", " ").replace("-", " ").upper()


def build_query_intent_note(query: str, sensor_snapshot: Dict[str, Any]) -> str:
    """Build a concise, query-aware note for UI agent chat replies."""
    lowered = query.strip().lower()
    if not lowered:
        return ""

    if any(term in lowered for term in ("sensor", "diagnostic", "status", "active", "reading")):
        if sensor_snapshot:
            sensor_ids = [str(sensor_id) for sensor_id in sensor_snapshot.keys()]
            sample = ", ".join(sensor_ids[:6])
            if len(sensor_ids) > 6:
                sample = f"{sample}, ..."
            return f"Active sensor streams: {sample}."
        return "No active sensor streams were available in this snapshot."

    if any(term in lowered for term in ("hello", "hi", "hey", "lol")):
        return "Greeting acknowledged. Library Computer remains on active watch."

    return "Query captured and correlated with current tricorder context."


def build_sensor_catalog(config: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """Build a lightweight UI-safe catalog of configured sensors."""
    catalog: Dict[str, Dict[str, str]] = {}
    sensors_config = config.get("sensors", {})
    if not isinstance(sensors_config, dict):
        return catalog

    for group_name, source in SENSOR_GROUPS.items():
        group = sensors_config.get(group_name, {})
        if not isinstance(group, dict):
            continue

        for sensor_id, raw_cfg in group.items():
            if not isinstance(sensor_id, str):
                continue
            sensor_cfg = raw_cfg if isinstance(raw_cfg, dict) else {}
            label = str(sensor_cfg.get("label") or display_label(sensor_id))
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
            label = str(channel_cfg.get("label") or display_label(channel_id))
            catalog[f"ads1263:{channel_id}"] = {
                "id": f"ads1263:{channel_id}",
                "label": label,
                "source": "adc_channel",
            }

    return catalog


def sanitize_ui_config(
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

    sensor_catalog = build_sensor_catalog(full_config)
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
                    "label": display_label(sensor_id),
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
        "anomaly_ack_db_path": str(ui_config.get("anomaly_ack_db_path", "")),
        "anomaly_ack_persistent": bool(ui_config.get("anomaly_ack_db_path", "")),
        "anomaly_alert_threshold": float(ui_config.get("anomaly_alert_threshold", DEFAULT_SEVERITY_THRESHOLDS["high"])),
        "anomaly_history_path": str(ui_config.get("anomaly_history_path", "/ui/anomalies/history")),
        "anomaly_history_page_size": int(ui_config.get("anomaly_history_page_size", 50)),
        "agent_enabled": bool(ui_config.get("agent_enabled", True)),
        "agent_chat_path": str(ui_config.get("agent_chat_path", DEFAULT_UI_AGENT_CHAT_PATH)),
        "reconnect_initial_ms": int(ui_config.get("reconnect_initial_ms", 1500)),
        "reconnect_max_ms": int(ui_config.get("reconnect_max_ms", 10000)),
        "panel_order": panel_order,
        "panels": panels,
        "sensor_catalog": sensor_catalog,
    }
