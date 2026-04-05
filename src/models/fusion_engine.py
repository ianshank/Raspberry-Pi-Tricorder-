"""Sensor fusion engine (cross-attention transformer) for multi-sensor integration."""

import time
from typing import Any, Dict
import logging

import numpy as np

from models.base import (
    BaseModel, ModelResult, ModelStatus, ModelLoadError,
    ModelInferenceError, ModelRegistry, InferenceAdapter,
)

logger = logging.getLogger(__name__)


class FusionEngine(BaseModel):
    """
    Cross-attention transformer for multi-sensor fusion.

    Takes tokenized sensor embeddings and produces a unified scene embedding.
    """

    def __init__(self, model_id: str, adapter: InferenceAdapter, config: Dict[str, Any]):
        super().__init__(model_id, adapter, config)
        self.input_shape = config.get("input_shape", [1, 16, 64])
        self.output_shape = config.get("output_shape", [1, 512])
        self.confidence_threshold = config.get("confidence_threshold", 0.80)

    def load(self) -> bool:
        try:
            model_path = self.config.get("model_path", "")
            success = self.adapter.load(model_path)
            if not success:
                raise ModelLoadError(f"Adapter failed to load: {model_path}")
            self.status = ModelStatus.LOADED
            logger.info("%s loaded from %s", self.model_id, model_path)
            return True
        except Exception as e:
            self._record_error(e)
            raise ModelLoadError(f"Failed to load fusion engine: {e}") from e

    def predict(self, input_data: np.ndarray) -> ModelResult:
        try:
            self.status = ModelStatus.RUNNING
            start_time = time.monotonic()

            expected = tuple(self.input_shape)
            if input_data.shape != expected:
                if input_data.size == np.prod(expected):
                    logger.debug("%s reshaping input %s -> %s",
                                 self.model_id, input_data.shape, expected)
                    input_data = input_data.reshape(expected)
                else:
                    raise ModelInferenceError(
                        f"Input shape mismatch: expected {expected}, got {input_data.shape}"
                    )

            scene_embedding = self.adapter.predict(input_data)

            # Compute confidence from embedding magnitude
            embedding_norm = float(np.linalg.norm(scene_embedding))
            confidence = min(1.0, embedding_norm / max(np.prod(self.output_shape), 1))

            elapsed_ms = (time.monotonic() - start_time) * 1000
            self._record_inference(elapsed_ms)
            self.status = ModelStatus.LOADED

            return ModelResult(
                output={
                    "scene_embedding": scene_embedding.tolist() if hasattr(scene_embedding, 'tolist') else scene_embedding,
                    "embedding_dim": scene_embedding.shape[-1] if hasattr(scene_embedding, 'shape') else len(scene_embedding),
                    "embedding_norm": round(embedding_norm, 4),
                },
                confidence=round(confidence, 4),
                inference_time_ms=round(elapsed_ms, 2),
                metadata={"model_id": self.model_id},
            )
        except ModelInferenceError:
            raise
        except Exception as e:
            logger.error("%s fusion predict failed: %s", self.model_id, e)
            self._record_error(e)
            raise ModelInferenceError(f"Fusion failed: {e}") from e

    def fuse_sensor_readings(self, sensor_embeddings: Dict[str, np.ndarray]) -> ModelResult:
        """
        Fuse multiple sensor embeddings into a scene representation.

        Args:
            sensor_embeddings: Dict mapping sensor_id -> embedding vector
        """
        if not sensor_embeddings:
            raise ModelInferenceError("No sensor embeddings provided")

        logger.debug("Fusing %d sensor embeddings", len(sensor_embeddings))

        # Stack embeddings into token sequence
        embeddings = list(sensor_embeddings.values())
        max_dim = max(e.shape[-1] for e in embeddings)

        # Pad embeddings to same dimension
        padded = []
        for emb in embeddings:
            if emb.ndim == 1:
                emb = emb.reshape(1, -1)
            if emb.shape[-1] < max_dim:
                pad_width = max_dim - emb.shape[-1]
                emb = np.pad(emb, ((0, 0), (0, pad_width)))
            padded.append(emb)

        token_sequence = np.concatenate(padded, axis=0)

        # Reshape to match expected input shape
        expected = tuple(self.input_shape)
        batch_tokens = token_sequence.reshape(1, *token_sequence.shape)

        # Pad/truncate to expected shape
        if batch_tokens.shape[1] < expected[1]:
            pad = np.zeros((1, expected[1] - batch_tokens.shape[1], batch_tokens.shape[2]))
            batch_tokens = np.concatenate([batch_tokens, pad], axis=1)
        elif batch_tokens.shape[1] > expected[1]:
            batch_tokens = batch_tokens[:, :expected[1], :]

        if batch_tokens.shape[2] < expected[2]:
            pad = np.zeros((1, batch_tokens.shape[1], expected[2] - batch_tokens.shape[2]))
            batch_tokens = np.concatenate([batch_tokens, pad], axis=2)
        elif batch_tokens.shape[2] > expected[2]:
            batch_tokens = batch_tokens[:, :, :expected[2]]

        return self.predict(batch_tokens)


ModelRegistry.register_type("fusion_transformer", FusionEngine)
