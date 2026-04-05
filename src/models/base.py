"""Base neural network model framework with dependency injection."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import time
import logging

import numpy as np

logger = logging.getLogger(__name__)


class ModelStatus(Enum):
    """Model lifecycle status."""
    UNLOADED = "unloaded"
    LOADED = "loaded"
    RUNNING = "running"
    ERROR = "error"


@dataclass
class ModelResult:
    """Standard model inference result."""
    output: Any
    confidence: float = 1.0
    inference_time_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        val = self.output
        if hasattr(val, 'tolist'):
            val = val.tolist()
        return {
            "output": val,
            "confidence": self.confidence,
            "inference_time_ms": self.inference_time_ms,
            "metadata": self.metadata,
        }


@runtime_checkable
class InferenceAdapter(Protocol):
    """Protocol for NN inference backends (ONNX, HailoRT, mock)."""

    def load(self, model_path: str) -> bool: ...
    def predict(self, input_data: np.ndarray) -> np.ndarray: ...
    def get_info(self) -> Dict[str, Any]: ...


class BaseModel(ABC):
    """Abstract base class for all neural network model wrappers."""

    def __init__(self, model_id: str, adapter: InferenceAdapter, config: Dict[str, Any]):
        self.model_id = model_id
        self.adapter = adapter
        self.config = config
        self.status = ModelStatus.UNLOADED
        self._inference_count = 0
        self._error_count = 0
        self._total_inference_time_ms = 0.0
        logger.info("Created model: %s", model_id)

    @abstractmethod
    def load(self) -> bool:
        """Load model weights into inference engine."""
        pass

    @abstractmethod
    def predict(self, input_data: np.ndarray) -> ModelResult:
        """Run inference on input data."""
        pass

    def get_info(self) -> Dict[str, Any]:
        avg_time = (
            self._total_inference_time_ms / self._inference_count
            if self._inference_count > 0
            else 0.0
        )
        return {
            "model_id": self.model_id,
            "status": self.status.value,
            "inference_count": self._inference_count,
            "error_count": self._error_count,
            "avg_inference_time_ms": round(avg_time, 2),
            "config": {
                "model_path": self.config.get("model_path"),
                "input_shape": self.config.get("input_shape"),
                "output_shape": self.config.get("output_shape"),
                "quantization": self.config.get("quantization"),
            },
        }

    def _record_inference(self, elapsed_ms: float) -> None:
        self._inference_count += 1
        self._total_inference_time_ms += elapsed_ms

    def _record_error(self, error: Exception) -> None:
        self._error_count += 1
        self.status = ModelStatus.ERROR
        logger.error("%s inference error: %s", self.model_id, error, exc_info=True)


class ModelError(Exception):
    """Base exception for model-related errors."""
    pass


class ModelLoadError(ModelError):
    """Raised when model loading fails."""
    pass


class ModelInferenceError(ModelError):
    """Raised when model inference fails."""
    pass


class ModelRegistry:
    """Registry for model instances."""

    _registry: Dict[str, type] = {}
    _instances: Dict[str, BaseModel] = {}

    @classmethod
    def register_type(cls, model_type: str, model_class: type) -> None:
        cls._registry[model_type] = model_class
        logger.info("Registered model type: %s", model_type)

    @classmethod
    def create(
        cls, model_type: str, model_id: str, adapter: InferenceAdapter, config: Dict[str, Any]
    ) -> BaseModel:
        if model_type not in cls._registry:
            raise ValueError(
                f"Unknown model type: {model_type}. Available: {list(cls._registry.keys())}"
            )
        instance = cls._registry[model_type](model_id, adapter, config)
        cls._instances[model_id] = instance
        return instance

    @classmethod
    def get(cls, model_id: str) -> Optional[BaseModel]:
        return cls._instances.get(model_id)

    @classmethod
    def list_types(cls) -> List[str]:
        return list(cls._registry.keys())

    @classmethod
    def list_instances(cls) -> List[str]:
        return list(cls._instances.keys())

    @classmethod
    def clear(cls) -> None:
        cls._registry.clear()
        cls._instances.clear()
