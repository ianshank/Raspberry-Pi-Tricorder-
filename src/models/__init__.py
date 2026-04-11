"""Neural network models package."""

# Import models to trigger registration
import models.anomaly_detector  # noqa: F401
import models.fusion_engine  # noqa: F401
from models.base import (
    BaseModel,
    InferenceAdapter,
    ModelError,
    ModelInferenceError,
    ModelLoadError,
    ModelRegistry,
    ModelResult,
    ModelStatus,
)

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
