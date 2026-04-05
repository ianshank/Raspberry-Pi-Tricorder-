"""Neural network models package."""

from models.base import (
    BaseModel,
    ModelResult,
    ModelStatus,
    ModelError,
    ModelLoadError,
    ModelInferenceError,
    ModelRegistry,
    InferenceAdapter,
)

# Import models to trigger registration
import models.anomaly_detector  # noqa: F401
import models.fusion_engine  # noqa: F401

__all__ = [
    "BaseModel",
    "ModelResult",
    "ModelStatus",
    "ModelError",
    "ModelLoadError",
    "ModelInferenceError",
    "ModelRegistry",
    "InferenceAdapter",
]
