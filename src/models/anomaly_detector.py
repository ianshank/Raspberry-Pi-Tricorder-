"""Anomaly detector model (Autoencoder-LSTM) for sensor data monitoring."""

import time
from typing import Any, Dict
import logging

import numpy as np

from models.base import (
    BaseModel, ModelResult, ModelStatus, ModelLoadError,
    ModelInferenceError, ModelRegistry, InferenceAdapter,
)

logger = logging.getLogger(__name__)


class AnomalyDetector(BaseModel):
    """
    Autoencoder-LSTM anomaly detector.

    Monitors sensor data streams for anomalies by computing
    reconstruction error against learned normal patterns.
    """

    def __init__(self, model_id: str, adapter: InferenceAdapter, config: Dict[str, Any]):
        super().__init__(model_id, adapter, config)
        self.window_size = config.get("window_size", 256)
        self.confidence_threshold = config.get("confidence_threshold", 0.75)
        self.input_shape = config.get("input_shape", [1, 256, 10])
        self.output_shape = config.get("output_shape", [1, 10])
        self._baseline_mse: float = 0.0
        
        # Validate and normalize max_history
        self.max_history = self._get_valid_max_history(config.get("max_history", 1000))
        self._anomaly_history: list = []

    @staticmethod
    def _get_valid_max_history(max_history: Any) -> int:
        """Validate max_history: clamp to minimum 1.
        
        Args:
            max_history: Raw config value (may be invalid)
            
        Returns:
            Valid max_history value (minimum 1)
            
        Raises:
            ValueError: If max_history is not numeric
        """
        if not isinstance(max_history, (int, float)):
            raise ValueError(f"max_history must be numeric, got {type(max_history).__name__}")
        
        clamped = max(1, int(max_history))
        if clamped != int(max_history):
            logger.warning(
                "max_history %s clamped to valid range [1, inf): using %d",
                max_history, clamped
            )
        return clamped

    def load(self) -> bool:
        try:
            model_path = self.config.get("model_path", "")
            success = self.adapter.load(model_path)
            if not success:
                raise ModelLoadError(f"Adapter failed to load model: {model_path}")
            self.status = ModelStatus.LOADED
            logger.info("%s loaded from %s", self.model_id, model_path)
            return True
        except Exception as e:
            self._record_error(e)
            raise ModelLoadError(f"Failed to load anomaly detector: {e}") from e

    def predict(self, input_data: np.ndarray) -> ModelResult:
        try:
            self.status = ModelStatus.RUNNING
            start_time = time.monotonic()

            # Validate input shape
            expected = tuple(self.input_shape)
            if input_data.shape != expected:
                # Try to reshape if total elements match
                if input_data.size == np.prod(expected):
                    input_data = input_data.reshape(expected)
                else:
                    raise ModelInferenceError(
                        f"Input shape mismatch: expected {expected}, got {input_data.shape}"
                    )

            # Run inference
            reconstruction = self.adapter.predict(input_data)

            # Compute reconstruction error
            original_flat = input_data.reshape(input_data.shape[0], -1)
            recon_flat = reconstruction.reshape(reconstruction.shape[0], -1)

            # Handle different output shapes
            if recon_flat.shape[1] < original_flat.shape[1]:
                original_flat = original_flat[:, :recon_flat.shape[1]]

            mse = float(np.mean((original_flat - recon_flat) ** 2))
            anomaly_score = min(1.0, mse / max(self._baseline_mse, 1e-6))

            is_anomaly = anomaly_score > self.confidence_threshold

            elapsed_ms = (time.monotonic() - start_time) * 1000
            self._record_inference(elapsed_ms)
            self.status = ModelStatus.LOADED

            # Record to history
            result_entry = {
                "anomaly_score": round(anomaly_score, 4),
                "mse": round(mse, 6),
                "is_anomaly": is_anomaly,
            }
            self._anomaly_history.append(result_entry)
            # Keep last max_history entries
            if len(self._anomaly_history) > self.max_history:
                self._anomaly_history = self._anomaly_history[-self.max_history:]

            return ModelResult(
                output={
                    "anomaly_score": round(anomaly_score, 4),
                    "reconstruction_mse": round(mse, 6),
                    "is_anomaly": is_anomaly,
                    "threshold": self.confidence_threshold,
                },
                confidence=1.0 - anomaly_score if not is_anomaly else anomaly_score,
                inference_time_ms=round(elapsed_ms, 2),
                metadata={"model_id": self.model_id, "window_size": self.window_size},
            )
        except ModelInferenceError:
            raise
        except Exception as e:
            logger.error("%s anomaly detection failed: %s", self.model_id, e)
            self._record_error(e)
            raise ModelInferenceError(f"Anomaly detection failed: {e}") from e

    def set_baseline(self, baseline_data: np.ndarray) -> None:
        """Compute baseline MSE from known-normal data."""
        try:
            reconstruction = self.adapter.predict(baseline_data)
            original_flat = baseline_data.reshape(baseline_data.shape[0], -1)
            recon_flat = reconstruction.reshape(reconstruction.shape[0], -1)
            if recon_flat.shape[1] < original_flat.shape[1]:
                original_flat = original_flat[:, :recon_flat.shape[1]]
            self._baseline_mse = float(np.mean((original_flat - recon_flat) ** 2))
            logger.info("%s baseline MSE set to %.6f", self.model_id, self._baseline_mse)
        except Exception as e:
            logger.error("%s baseline computation failed: %s", self.model_id, e)

    def get_anomaly_history(self, limit: int = 100) -> list:
        return self._anomaly_history[-limit:]


ModelRegistry.register_type("anomaly_detector", AnomalyDetector)
