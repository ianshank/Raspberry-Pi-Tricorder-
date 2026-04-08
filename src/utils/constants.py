"""Shared constants for the Tricorder Neural Platform.

Centralizes magic numbers, threshold defaults, and enumeration values
that are referenced by multiple modules.
"""

from typing import Dict, FrozenSet, Tuple

# ---------------------------------------------------------------------------
# Severity thresholds used by both the MCP server anomaly pipeline and
# the LangGraph agent for consistent severity classification.
# ---------------------------------------------------------------------------
DEFAULT_SEVERITY_THRESHOLDS: Dict[str, float] = {
    "critical": 0.9,
    "high": 0.75,
    "medium": 0.5,
}

SEVERITY_LEVELS: Tuple[str, ...] = ("critical", "high", "medium")

# ---------------------------------------------------------------------------
# Sensor configuration group names mapped to their transport source label.
# Used when iterating over enabled sensors in config dicts.
# ---------------------------------------------------------------------------
SENSOR_GROUPS: Dict[str, str] = {
    "i2c_devices": "i2c",
    "spi_devices": "spi",
    "uart_devices": "uart",
}

# ---------------------------------------------------------------------------
# MQTT topic suffixes (appended to the configured topic_prefix)
# ---------------------------------------------------------------------------
MQTT_TOPIC_SENSORS: str = "sensors"
MQTT_TOPIC_ANOMALIES: str = "anomalies"
MQTT_TOPIC_ACK: str = "anomalies/ack"
MQTT_DEFAULT_QOS: int = 1
MQTT_DEFAULT_RECONNECT_DELAY_S: float = 5.0
MQTT_MAX_RECONNECT_DELAY_S: float = 60.0

# ---------------------------------------------------------------------------
# Admin API constants
# ---------------------------------------------------------------------------
ADMIN_HMAC_HEADER: str = "X-Tricorder-HMAC"
ADMIN_MAX_PAYLOAD_BYTES: int = 65536

# ---------------------------------------------------------------------------
# UI polling interval floors (milliseconds)
# ---------------------------------------------------------------------------
MIN_POLL_INTERVAL_MS: int = 100
MIN_ANOMALY_POLL_INTERVAL_MS: int = 250

# ---------------------------------------------------------------------------
# Anomaly history pagination limits
# ---------------------------------------------------------------------------
MIN_ANOMALY_HISTORY_PAGE_SIZE: int = 10
MAX_ANOMALY_HISTORY_PAGE_SIZE: int = 500
MIN_ACK_HISTORY_LIMIT: int = 1

# ---------------------------------------------------------------------------
# Auth middleware — public paths that skip API key checks
# ---------------------------------------------------------------------------
AUTH_PUBLIC_PATHS: FrozenSet[str] = frozenset({"/health", "/docs", "/openapi.json"})

# ---------------------------------------------------------------------------
# Request validation limits
# ---------------------------------------------------------------------------
AGENT_CHAT_QUERY_MAX_LENGTH: int = 4000

# ---------------------------------------------------------------------------
# SQLite pragmas (shared by ack_store and session_store)
# ---------------------------------------------------------------------------
SQLITE_BUSY_TIMEOUT_MS: int = 5000

# ---------------------------------------------------------------------------
# Model inference performance thresholds
# ---------------------------------------------------------------------------
INFERENCE_WARN_THRESHOLD_MS: float = 100.0

# ---------------------------------------------------------------------------
# Simulation defaults
# ---------------------------------------------------------------------------
SIMULATED_SENSOR_CONFIDENCE: float = 0.92
