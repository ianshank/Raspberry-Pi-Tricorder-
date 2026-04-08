"""Anomaly detector model (Autoencoder-LSTM) for sensor data monitoring."""

import time
from typing import Any, Dict
import logging

import numpy as np

from models.base import (
    BaseModel, ModelResult, ModelStatus, ModelLoadError,
    ModelInferenceError, ModelRegistry, InferenceAdapter,
    validate_model_input,
)
from utils.constants import INFERENCE_WARN_THRESHOLD_MS

logger = logging.getLogger(__name__)


class AnomalyDetector(BaseModel):
    """
    Autoencoder-LSTM anomaly detector.

    Monitors sensor data streams for anomalies by computing
    reconstruction error against learned normal patterns.
    """

    DEFAULT_MAX_HISTORY = 1000

    @staticmethod
    def _get_valid_max_history(config: Dict[str, Any]) -> int:
        raw_max_history = config.get("max_history", AnomalyDetector.DEFAULT_MAX_HISTORY)
        try:
            max_history = int(raw_max_history)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid max_history=%r; using default=%d",
                raw_max_history,
                AnomalyDetector.DEFAULT_MAX_HISTORY,
            )
            max_history = AnomalyDetector.DEFAULT_MAX_HISTORY

        if max_history < 1:
            logger.warning("max_history=%d is invalid; clamping to 1", max_history)
            return 1
        return max_history

    def __init__(self, model_id: str, adapter: InferenceAdapter, config: Dict[str, Any]):
        super().__init__(model_id, adapter, config)
        self.window_size = config.get("window_size", 256)
        self.confidence_threshold = config.get("confidence_threshold", 0.75)
        self.input_shape = config.get("input_shape", [1, 256, 10])
        self.output_shape = config.get("output_shape", [1, 10])
        self.max_history = self._get_valid_max_history(config)
        self._baseline_mse: float = 0.0
        self._anomaly_history: list = []

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

            # Validate input values and shape
            validate_model_input(input_data, name=f"{self.model_id}_input")
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
            if elapsed_ms > INFERENCE_WARN_THRESHOLD_MS:
                logger.warning(
                    "%s inference slow: %.1fms (threshold: %.0fms)",
                    self.model_id, elapsed_ms, INFERENCE_WARN_THRESHOLD_MS,
                )
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

    def get_anomaly_history(self, limit: int = 100) -> list:
        return self._anomaly_history[-limit:]


ModelRegistry.register_type("anomaly_detector", AnomalyDetector)
