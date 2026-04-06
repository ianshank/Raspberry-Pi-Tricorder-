"""MCP tools for anomaly detection operations."""

from typing import Any, Dict, List, Optional
import logging

import numpy as np

from models.base import ModelRegistry

logger = logging.getLogger(__name__)

DEFAULT_MAX_SENSOR_DATA_ITEMS = 10_000
GENERIC_ANOMALY_SCAN_ERROR = "Anomaly scan operation failed. Check logs for details."


def _exceeds_total_item_limit(value: Any, limit: int) -> bool:
    """Return True when a nested list/tuple payload contains more than *limit* scalar items.

    Uses iterative stack traversal to avoid recursion depth limits on deeply
    nested payloads.
    """
    total_items = 0
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, (list, tuple)):
            stack.extend(current)
            continue
        total_items += 1
        if total_items > limit:
            return True
    return False


def register_anomaly_tools(
    registry: Any,
    max_sensor_data_items: int = DEFAULT_MAX_SENSOR_DATA_ITEMS,
) -> None:
    """Register anomaly detection MCP tools.

    Args:
        registry: Tool registry to register with.
        max_sensor_data_items: Upper bound on sensor_data array length.
    """
    effective_limit = max_sensor_data_items
    if (
        isinstance(effective_limit, bool)
        or not isinstance(effective_limit, int)
        or effective_limit < 1
    ):
        logger.warning(
            "Invalid max_sensor_data_items=%r; falling back to default %d",
            max_sensor_data_items,
            DEFAULT_MAX_SENSOR_DATA_ITEMS,
        )
        effective_limit = DEFAULT_MAX_SENSOR_DATA_ITEMS

    def run_anomaly_scan(
        model_id: str = "anomaly_detector",
        sensor_data: Optional[List[Any]] = None,
    ) -> Dict[str, Any]:
        """Run anomaly detection on provided or buffered sensor data."""
        model = ModelRegistry.get(model_id)
        if model is None:
            return {"error": f"Model not found: {model_id}"}

        try:
            if sensor_data is not None:
                if not isinstance(sensor_data, (list, tuple)):
                    return {"error": "sensor_data must be a list or tuple"}
                if _exceeds_total_item_limit(sensor_data, effective_limit):
                    return {
                        "error": (
                            f"sensor_data exceeds maximum item count "
                            f"({effective_limit})"
                        )
                    }
                input_array = np.array(sensor_data, dtype=np.float32)
                # Defense-in-depth: reject if numpy materialized more elements
                # than the limit (e.g. via broadcasting or unexpected coercion).
                if input_array.size > effective_limit:
                    return {
                        "error": (
                            f"sensor_data exceeds maximum item count "
                            f"({effective_limit})"
                        )
                    }
                if not np.all(np.isfinite(input_array)):
                    return {"error": "sensor_data contains non-finite values"}
            else:
                # Generate zero input as placeholder when no data provided
                input_shape = getattr(model, "input_shape", None)
                if input_shape is None:
                    model_config = getattr(model, "config", None)
                    if isinstance(model_config, dict):
                        input_shape = model_config.get("input_shape")

                if input_shape is None:
                    raise ValueError(
                        f"Model {model_id} does not define an input shape for placeholder generation"
                    )

                input_array = np.zeros(input_shape, dtype=np.float32)

            result = model.predict(input_array)
            return result.to_dict()
        except Exception as e:
            logger.error("run_anomaly_scan failed: %s", e, exc_info=True)
            return {"error": GENERIC_ANOMALY_SCAN_ERROR}

    registry.register_function(
        name="run_anomaly_scan",
        description="Run anomaly detection on sensor data",
        input_schema={
            "type": "object",
            "properties": {
                "model_id": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 128,
                    "description": "Anomaly model ID",
                    "default": "anomaly_detector",
                },
                "sensor_data": {
                    "type": "array",
                    "maxItems": effective_limit,
                    "description": "Optional sensor data array. If omitted, uses buffered data.",
                },
            },
        },
        func=run_anomaly_scan,
    )

    def get_anomaly_history(
        model_id: str = "anomaly_detector",
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Get recent anomaly detection history."""
        model = ModelRegistry.get(model_id)
        if model is None:
            return {"error": f"Model not found: {model_id}"}

        if not hasattr(model, 'get_anomaly_history'):
            return {"error": f"Model {model_id} does not support anomaly history"}

        history = model.get_anomaly_history(limit=limit)
        return {
            "model_id": model_id,
            "entries": history,
            "count": len(history),
        }

    registry.register_function(
        name="get_anomaly_history",
        description="Get recent anomaly detection results",
        input_schema={
            "type": "object",
            "properties": {
                "model_id": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 128,
                    "default": "anomaly_detector",
                },
                "limit": {"type": "integer", "default": 100, "minimum": 1, "maximum": 1000},
            },
        },
        func=get_anomaly_history,
    )
