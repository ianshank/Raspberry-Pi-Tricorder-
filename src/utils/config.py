"""
Configuration management for Tricorder Neural Platform.

All configuration is externalized to YAML files with environment variable overrides.
NO hardcoded values in application code.
"""

from typing import Any, Callable, Dict, List, Literal, Optional
from pathlib import Path
import copy
import os
import json
import threading
import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, Field, field_validator, model_validator
from utils.constants import DEFAULT_SEVERITY_THRESHOLDS
import logging

logger = logging.getLogger(__name__)


LCARS_COLORS = {
    "anakiwa",
    "atomic-tangerine",
    "bahama-blue",
    "blue",
    "blue-bell",
    "bourbon",
    "chestnut-rose",
    "cosmic",
    "danub",
    "dodger-blue",
    "dodger-blue-alt",
    "eggplant",
    "golden-tanoi",
    "gray",
    "hopbush",
    "husk",
    "indigo",
    "lavender-purple",
    "lilac",
    "mariner",
    "medium-carmine",
    "melrose",
    "navy-blue",
    "neon-carrot",
    "orange-peel",
    "pale-canary",
    "periwinkle",
    "red-alert",
    "red-damask",
    "rust",
    "sandy-brown",
    "tamarillo",
    "white",
}


class I2CDeviceConfig(BaseModel):
    """Configuration for an I2C sensor device."""
    address: int = Field(..., ge=0x00, le=0x7F, description="7-bit I2C address")
    bus: int = Field(default=1, ge=0, le=10, description="I2C bus number")
    enabled: bool = Field(default=True, description="Whether device is enabled")
    poll_rate_hz: float = Field(default=1.0, gt=0, le=100, description="Polling rate in Hz")
    timeout_ms: int = Field(default=1000, gt=0, description="I2C transaction timeout in ms")

    @field_validator('address')
    @classmethod
    def validate_address(cls, v: int) -> int:
        if v < 0x03 or v > 0x77:
            raise ValueError(f"I2C address 0x{v:02X} is outside valid range (0x03-0x77)")
        return v


class SPIDeviceConfig(BaseModel):
    """Configuration for an SPI device."""
    bus: int = Field(default=0, ge=0, le=10)
    device: int = Field(default=0, ge=0, le=10)
    max_speed_hz: int = Field(default=1000000, gt=0, le=50000000)
    mode: int = Field(default=1, ge=0, le=3, description="SPI mode (0-3)")
    bits_per_word: int = Field(default=8, ge=8, le=16)
    cs_gpio: int = Field(default=8, description="Chip select GPIO pin")
    drdy_gpio: int = Field(default=17, description="Data ready interrupt GPIO pin")
    reset_gpio: int = Field(default=27, description="Reset GPIO pin")
    enabled: bool = Field(default=True)


class UARTDeviceConfig(BaseModel):
    """Configuration for a UART device."""
    port: str = Field(default="/dev/ttyAMA0")
    baud_rate: int = Field(default=115200, gt=0)
    timeout_s: float = Field(default=1.0, gt=0)
    enabled: bool = Field(default=True)


class ADCChannelConfig(BaseModel):
    """Configuration for a single ADC channel pair."""
    positive_input: int = Field(..., ge=0, le=9, description="Positive analog input number")
    negative_input: int = Field(..., ge=0, le=9, description="Negative analog input number")
    label: str = Field(..., description="Human-readable label for this channel")
    gain: int = Field(default=1, ge=1, le=64, description="PGA gain setting")
    data_rate: int = Field(default=20, description="Samples per second")


class SensorConfig(BaseModel):
    """Top-level sensor hardware configuration."""
    i2c_devices: Dict[str, I2CDeviceConfig] = Field(default_factory=dict)
    spi_devices: Dict[str, SPIDeviceConfig] = Field(default_factory=dict)
    uart_devices: Dict[str, UARTDeviceConfig] = Field(default_factory=dict)
    adc_channels: Dict[str, ADCChannelConfig] = Field(default_factory=dict)


class ModelConfig(BaseModel):
    """Neural network model configuration."""
    model_path: str = Field(..., description="Path to model file")
    input_shape: List[int] = Field(..., description="Model input shape")
    output_shape: List[int] = Field(..., description="Model output shape")
    quantization: str = Field(default="int8")
    hailo_hef_path: Optional[str] = None
    batch_size: int = Field(default=1, gt=0, le=32)
    confidence_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    window_size: int = Field(default=256, gt=0, description="Sliding window size for time-series models")

    @field_validator('quantization')
    @classmethod
    def validate_quantization(cls, v: str) -> str:
        valid = {"fp32", "fp16", "int8", "int4"}
        if v not in valid:
            raise ValueError(f"Quantization must be one of {valid}, got {v}")
        return v


class MCPServerConfig(BaseModel):
    """MCP server configuration."""
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8000, gt=1024, le=65535)
    transport: str = Field(default="http")
    auth_enabled: bool = Field(default=False)
    api_key: Optional[str] = None
    max_concurrent_tools: int = Field(default=10, gt=0, le=100)
    health_detailed_enabled: bool = Field(
        default=True,
        description="Enable the /health/detailed endpoint with per-sensor status",
    )
    operator_map: Dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of API key/token to operator_id for identity derivation",
    )

    @field_validator('transport')
    @classmethod
    def validate_transport(cls, v: str) -> str:
        valid = {"http", "stdio"}
        if v not in valid:
            raise ValueError(f"Transport must be one of {valid}, got {v}")
        return v


class LangGraphAgentConfig(BaseModel):
    """LangGraph agent configuration."""
    llm_endpoint: str = Field(default="http://localhost:11434")
    model_name: str = Field(default="qwen2.5:3b")
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_tokens: int = Field(default=512, gt=0, le=4096)
    checkpoint_db_path: str = Field(default="data/agent_checkpoints.db")
    mission_mode: str = Field(default="patrol")
    human_in_loop_threshold: str = Field(default="HIGH")
    severity_thresholds: Dict[str, float] = Field(
        default_factory=lambda: DEFAULT_SEVERITY_THRESHOLDS.copy(),
        description="Anomaly score thresholds for severity classification",
    )
    max_tools_per_iteration: int = Field(default=3, gt=0, le=20)
    max_iterations: int = Field(default=5, gt=0, le=50)
    llm_timeout_s: float = Field(
        default=30.0,
        gt=0,
        le=300,
        description="HTTP timeout for LLM calls in seconds",
    )

    @field_validator('mission_mode')
    @classmethod
    def validate_mission_mode(cls, v: str) -> str:
        valid = {"patrol", "investigation", "cbrn", "maintenance"}
        if v not in valid:
            raise ValueError(f"Mission mode must be one of {valid}, got {v}")
        return v

    @field_validator('human_in_loop_threshold')
    @classmethod
    def validate_threshold(cls, v: str) -> str:
        valid = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
        if v not in valid:
            raise ValueError(f"Threshold must be one of {valid}, got {v}")
        return v

    @field_validator('severity_thresholds', mode='before')
    @classmethod
    def validate_severity_thresholds(cls, v: Any) -> Dict[str, float]:
        defaults = DEFAULT_SEVERITY_THRESHOLDS.copy()
        if v is None:
            return defaults.copy()
        if not isinstance(v, dict):
            raise ValueError("severity_thresholds must be a dictionary")

        allowed_keys = set(defaults)
        unknown_keys = set(v) - allowed_keys
        if unknown_keys:
            raise ValueError(
                "severity_thresholds contains unknown key(s): "
                f"{sorted(unknown_keys)}. Allowed keys are: {sorted(allowed_keys)}"
            )
        merged = defaults.copy()
        merged.update(v)

        normalized: Dict[str, float] = {}
        for key in defaults:
            try:
                value = float(merged[key])
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"severity_thresholds[{key!r}] must be a float between 0.0 and 1.0"
                ) from exc
            if not 0.0 <= value <= 1.0:
                raise ValueError(
                    f"severity_thresholds[{key!r}] must be between 0.0 and 1.0, got {value}"
                )
            normalized[key] = value

        if not (
            normalized["critical"] >= normalized["high"] >= normalized["medium"]
        ):
            raise ValueError("severity_thresholds must satisfy critical >= high >= medium")

        return normalized


class RAGConfig(BaseModel):
    """RAG vector database configuration."""
    db_path: str = Field(default="data/hazard_vectordb")
    embedding_model: str = Field(default="nomic-embed-text")
    collection_name: str = Field(default="hazard_references")
    top_k: int = Field(default=5, gt=0, le=20)
    similarity_threshold: float = Field(default=0.7, ge=0.0, le=1.0)


class MQTTConfig(BaseModel):
    """MQTT broker configuration."""
    host: str = Field(default="localhost")
    port: int = Field(default=1883, gt=0, le=65535)
    topic_prefix: str = Field(default="tricorder")
    keepalive_s: int = Field(default=60, gt=0)
    enabled: bool = Field(default=True)


class PanelConfig(BaseModel):
    """UI panel configuration."""

    label: str = Field(..., min_length=1, description="Human-readable panel title")
    sensors: List[str] = Field(default_factory=list, description="Ordered sensor IDs")
    color: str = Field(default="golden-tanoi", description="LCARS color name")

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str) -> str:
        if v not in LCARS_COLORS:
            raise ValueError(f"Unknown LCARS color: {v}")
        return v


class UIConfig(BaseModel):
    """Frontend UI configuration."""

    enabled: bool = Field(default=True, description="Enable built-in UI serving")
    static_dir: str = Field(
        default="src/ui/static",
        min_length=1,
        description="Static assets directory, relative to project root or absolute",
    )
    poll_interval_ms: int = Field(
        default=1000,
        ge=100,
        le=10000,
        description="Sensor stream polling interval in milliseconds",
    )
    ws_heartbeat_s: int = Field(
        default=30,
        ge=5,
        le=300,
        description="WebSocket heartbeat/keepalive interval in seconds",
    )
    ws_path: str = Field(
        default="/ws/sensors",
        min_length=1,
        description="WebSocket path used by the UI data service",
    )
    anomaly_ws_path: str = Field(
        default="/ws/anomalies",
        min_length=1,
        description="WebSocket path used for anomaly and alert streaming",
    )
    anomaly_poll_interval_ms: int = Field(
        default=2000,
        ge=250,
        le=60000,
        description="Polling cadence for anomaly stream in milliseconds",
    )
    anomaly_model_id: str = Field(
        default="anomaly_detector",
        min_length=1,
        description="Anomaly model ID used by streaming and chat context",
    )
    anomaly_history_limit: int = Field(
        default=1,
        ge=1,
        le=100,
        description="Maximum anomaly history entries attached to stream payloads",
    )
    anomaly_ack_enabled: bool = Field(
        default=True,
        description="Enable anomaly acknowledgment endpoint and UI controls",
    )
    anomaly_ack_path: str = Field(
        default="/ui/anomalies/ack",
        min_length=1,
        description="HTTP endpoint path used by UI anomaly acknowledgment actions",
    )
    anomaly_ack_history_limit: int = Field(
        default=500,
        ge=1,
        le=10000,
        description="Maximum number of acknowledged anomaly records kept",
    )
    anomaly_ack_db_path: str = Field(
        default="data/anomaly_ack.db",
        description="SQLite path for persistent ACK storage. "
                    "Empty string disables persistence (in-memory fallback).",
    )
    anomaly_alert_threshold: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="Fallback anomaly threshold when model output omits anomaly flag",
    )
    anomaly_history_path: str = Field(
        default="/ui/anomalies/history",
        min_length=1,
        description="REST endpoint path for paginated ACK history",
    )
    anomaly_history_page_size: int = Field(
        default=50,
        ge=10,
        le=500,
        description="Default page size for anomaly history pagination",
    )
    agent_enabled: bool = Field(default=True, description="Enable backend agent chat endpoint")
    agent_chat_path: str = Field(
        default="/ui/agent/chat",
        min_length=1,
        description="HTTP endpoint path used by UI agent chat panel",
    )
    agent_chat_stream_path: str = Field(
        default="/ui/agent/chat/stream",
        min_length=1,
        description="SSE endpoint path for streaming agent chat responses",
    )
    reconnect_initial_ms: int = Field(
        default=1500,
        ge=250,
        le=120000,
        description="Initial reconnect delay for websocket in milliseconds",
    )
    reconnect_max_ms: int = Field(
        default=10000,
        ge=500,
        le=300000,
        description="Maximum reconnect delay for websocket in milliseconds",
    )
    theme: Literal["classic", "enterprise", "defiant"] = Field(default="classic")
    debug: bool = Field(default=False, description="Enable extra UI diagnostics")
    panel_order: List[str] = Field(
        default_factory=list,
        description="Optional ordered panel keys; defaults to config declaration order",
    )
    panels: Dict[str, PanelConfig] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}

    @field_validator("ws_path", "anomaly_ws_path", "agent_chat_path", "agent_chat_stream_path", "anomaly_ack_path", "anomaly_history_path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        if not v.startswith("/"):
            raise ValueError("Path values must start with '/'")
        return v

    @model_validator(mode="after")
    def validate_reconnect_bounds(self) -> "UIConfig":
        if self.reconnect_max_ms < self.reconnect_initial_ms:
            raise ValueError("reconnect_max_ms must be >= reconnect_initial_ms")
        return self


class LoggingConfig(BaseModel):
    """Logging configuration."""
    level: str = Field(default="INFO")
    format: str = Field(default="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    file_path: Optional[str] = Field(default="logs/tricorder.log")
    max_bytes: int = Field(default=10485760, gt=0, description="10 MB default")
    backup_count: int = Field(default=5, ge=0, le=20)
    json_format: bool = Field(default=False, description="Emit structured JSON logs (production)")

    @field_validator('level')
    @classmethod
    def validate_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v not in valid:
            raise ValueError(f"Log level must be one of {valid}, got {v}")
        return v


class FeatureFlagsConfig(BaseModel):
    """Feature flags for toggling capabilities at runtime."""
    anomaly_ack: bool = Field(default=True, description="Enable anomaly acknowledgment endpoint")
    agent_chat: bool = Field(default=True, description="Enable agent chat endpoint")
    mqtt_publishing: bool = Field(default=True, description="Enable MQTT event publishing")
    llm_enabled: bool = Field(
        default=False,
        description="Enable LLM-based report synthesis (requires Ollama or compatible endpoint)",
    )
    agent_stream_enabled: bool = Field(
        default=False,
        description="Enable SSE streaming for agent chat responses",
    )


class AdminConfig(BaseModel):
    """Admin API configuration for dynamic config hot-reload."""
    enabled: bool = Field(default=False, description="Enable admin API endpoints")
    hmac_secret: Optional[str] = Field(
        default=None,
        description="HMAC-SHA256 secret for admin endpoint authentication",
    )
    allowed_sections: List[str] = Field(
        default_factory=lambda: ["ui", "logging", "feature_flags"],
        description="Config sections that can be hot-reloaded at runtime",
    )
    max_payload_bytes: int = Field(
        default=65536,
        gt=0,
        le=1048576,
        description="Maximum size of admin config update payload in bytes",
    )


class TricorderConfig(BaseModel):
    """Root configuration for the entire Tricorder platform."""
    project_name: str = Field(default="Tricorder Neural Platform")
    version: str = Field(default="1.0.0")
    environment: str = Field(default="development")

    sensors: SensorConfig = Field(default_factory=SensorConfig)
    models: Dict[str, ModelConfig] = Field(default_factory=dict)
    mcp_server: MCPServerConfig = Field(default_factory=MCPServerConfig)
    agent: LangGraphAgentConfig = Field(default_factory=LangGraphAgentConfig)
    rag: RAGConfig = Field(default_factory=RAGConfig)
    mqtt: MQTTConfig = Field(default_factory=MQTTConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    feature_flags: FeatureFlagsConfig = Field(default_factory=FeatureFlagsConfig)
    admin: AdminConfig = Field(default_factory=AdminConfig)

    model_config = {"extra": "forbid"}

    @field_validator('environment')
    @classmethod
    def validate_environment(cls, v: str) -> str:
        valid = {"development", "staging", "production"}
        if v not in valid:
            raise ValueError(f"Environment must be one of {valid}, got {v}")
        return v


def load_config(config_path: Optional[Path] = None) -> TricorderConfig:
    """
    Load configuration from YAML file with environment variable overrides.

    Args:
        config_path: Path to YAML config file. Defaults to config/base.yaml

    Returns:
        TricorderConfig instance
    """
    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "config" / "base.yaml"

    if not config_path.exists():
        logger.warning(f"Config file {config_path} not found, using defaults")
        config_dict: Dict[str, Any] = {}
    else:
        with open(config_path, 'r') as f:
            config_dict = yaml.safe_load(f) or {}

    config_dict = _apply_env_overrides(config_dict, prefix="TRICORDER")

    return TricorderConfig(**config_dict)


def _apply_env_overrides(config: Dict[str, Any], prefix: str = "TRICORDER") -> Dict[str, Any]:
    """
    Apply environment variable overrides to config dictionary.

    Uses double-underscore ``__`` as the nesting separator so that field
    names containing underscores (e.g. ``mcp_server``, ``json_format``)
    are preserved.

    TRICORDER__LOGGING__LEVEL=DEBUG  →  config['logging']['level']
    TRICORDER__MCP_SERVER__HOST=0.0.0.0  →  config['mcp_server']['host']
    """
    sep = "__"
    for env_key, env_value in os.environ.items():
        if not env_key.startswith(f"{prefix}{sep}"):
            continue

        keys = [k.lower() for k in env_key[len(prefix) + len(sep):].split(sep)]

        current = config
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            if not isinstance(current[key], dict):
                break
            current = current[key]
        else:
            try:
                parsed_value = json.loads(env_value)
            except (json.JSONDecodeError, ValueError):
                parsed_value = env_value

            current[keys[-1]] = parsed_value
            logger.debug(f"Applied env override: {env_key}")

    return config


# ---------------------------------------------------------------------------
# ConfigManager — thread-safe hot-reload with observer notifications
# ---------------------------------------------------------------------------

# Type alias for observer callbacks: (section_name, old_value, new_value)
ConfigObserver = Callable[[str, Any, Any], None]


class ConfigManager:
    """Thread-safe wrapper around TricorderConfig with hot-reload support.

    Observers are notified when specific config sections change, enabling
    runtime reconfiguration of logging level, feature flags, and UI settings.
    """

    def __init__(self, config: TricorderConfig) -> None:
        self._config = config
        self._lock = threading.Lock()
        self._observers: List[ConfigObserver] = []
        logger.info("ConfigManager initialised")

    @property
    def config(self) -> TricorderConfig:
        """Return the current config (read-only snapshot)."""
        with self._lock:
            return self._config

    def add_observer(self, observer: ConfigObserver) -> None:
        """Register a callback for config change notifications."""
        self._observers.append(observer)

    def get_sanitized(self) -> Dict[str, Any]:
        """Return current config as dict with secrets redacted."""
        with self._lock:
            data = self._config.model_dump()
        # Redact known secret fields
        if "mcp_server" in data and data["mcp_server"].get("api_key"):
            data["mcp_server"]["api_key"] = "***"
        if "admin" in data and data["admin"].get("hmac_secret"):
            data["admin"]["hmac_secret"] = "***"
        return data

    def reload(
        self,
        partial: Dict[str, Any],
        allowed_sections: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Apply a partial config update and return a diff of changes.

        Parameters
        ----------
        partial:
            Dict with section keys mapping to partial values, e.g.
            ``{"logging": {"level": "DEBUG"}}``.
        allowed_sections:
            List of section names that may be updated. If ``None``,
            uses the admin config's ``allowed_sections``.

        Returns
        -------
        Dict mapping section names to ``{"old": ..., "new": ...}`` diffs.

        Raises
        ------
        ValueError
            If a section is not in the allowed list or validation fails.
        """
        if allowed_sections is None:
            allowed_sections = self._config.admin.allowed_sections

        # Reject unknown sections
        for section in partial:
            if section not in allowed_sections:
                raise ValueError(
                    f"Section '{section}' is not allowed for hot-reload. "
                    f"Allowed: {allowed_sections}"
                )

        diff: Dict[str, Any] = {}
        with self._lock:
            current_dict = self._config.model_dump()

            for section, updates in partial.items():
                if not isinstance(updates, dict):
                    raise ValueError(f"Section '{section}' must be a dict")

                old_section = copy.deepcopy(current_dict.get(section, {}))
                # Merge updates into the section
                merged = copy.deepcopy(old_section)
                merged.update(updates)
                current_dict[section] = merged

                # Track what changed
                changed_keys = {
                    k for k in updates
                    if old_section.get(k) != updates[k]
                }
                if changed_keys:
                    diff[section] = {
                        "old": {k: old_section.get(k) for k in changed_keys},
                        "new": {k: merged[k] for k in changed_keys},
                    }

            # Validate the full config — raises ValidationError on failure
            new_config = TricorderConfig(**current_dict)
            self._config = new_config

        # Notify observers outside the lock
        for section, change in diff.items():
            for observer in self._observers:
                try:
                    observer(section, change["old"], change["new"])
                except Exception as exc:
                    logger.warning(
                        "Config observer failed for section '%s': %s",
                        section,
                        exc,
                    )

        if diff:
            logger.info("Config hot-reload applied: sections=%s", list(diff.keys()))
        return diff
