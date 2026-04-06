"""
Configuration management for Tricorder Neural Platform.

All configuration is externalized to YAML files with environment variable overrides.
NO hardcoded values in application code.
"""

from typing import Any, Dict, List, Optional
from pathlib import Path
import os
import json
import yaml
from pydantic import BaseModel, Field, field_validator
import logging

logger = logging.getLogger(__name__)


class I2CDeviceConfig(BaseModel):
    """Configuration for an I2C sensor device."""
    address: int = Field(..., ge=0x00, le=0x7F, description="7-bit I2C address")
    bus: int = Field(default=1, ge=0, le=10, description="I2C bus number")
    enabled: bool = Field(default=True, description="Whether device is enabled")
    poll_rate_hz: float = Field(default=1.0, gt=0, le=100, description="Polling rate in Hz")
    timeout_ms: int = Field(default=1000, gt=0, description="I2C transaction timeout in ms")

    @field_validator('address')
    @classmethod
    def validate_address(cls, v):
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
    def validate_quantization(cls, v):
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

    @field_validator('transport')
    @classmethod
    def validate_transport(cls, v):
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
        default={"critical": 0.9, "high": 0.75, "medium": 0.5},
        description="Anomaly score thresholds for severity classification",
    )
    max_tools_per_iteration: int = Field(default=3, gt=0, le=20)
    max_iterations: int = Field(default=5, gt=0, le=50)

    @field_validator('mission_mode')
    @classmethod
    def validate_mission_mode(cls, v):
        valid = {"patrol", "investigation", "cbrn", "maintenance"}
        if v not in valid:
            raise ValueError(f"Mission mode must be one of {valid}, got {v}")
        return v

    @field_validator('human_in_loop_threshold')
    @classmethod
    def validate_threshold(cls, v):
        valid = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
        if v not in valid:
            raise ValueError(f"Threshold must be one of {valid}, got {v}")
        return v


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


class LoggingConfig(BaseModel):
    """Logging configuration."""
    level: str = Field(default="INFO")
    format: str = Field(default="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    file_path: Optional[str] = Field(default="logs/tricorder.log")
    max_bytes: int = Field(default=10485760, gt=0, description="10 MB default")
    backup_count: int = Field(default=5, ge=0, le=20)

    @field_validator('level')
    @classmethod
    def validate_level(cls, v):
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v not in valid:
            raise ValueError(f"Log level must be one of {valid}, got {v}")
        return v


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
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    model_config = {"extra": "forbid"}

    @field_validator('environment')
    @classmethod
    def validate_environment(cls, v):
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

    TRICORDER_LOGGING_LEVEL=DEBUG overrides config['logging']['level']
    """
    for env_key, env_value in os.environ.items():
        if not env_key.startswith(f"{prefix}_"):
            continue

        keys = env_key[len(prefix) + 1:].lower().split('_')

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
