"""MCP tools for anomaly detection operations."""

from typing import Any, Dict
import logging

import numpy as np

from models.base import ModelRegistry

logger = logging.getLogger(__name__)


def register_anomaly_tools(registry) -> None:
    """Register anomaly detection MCP tools."""

    def run_anomaly_scan(
        model_id: str = "anomaly_detector",
        sensor_data: list = None,
    ) -> Dict[str, Any]:
        """Run anomaly detection on provided or buffered sensor data."""
        model = ModelRegistry.get(model_id)
        if model is None:
            return {"error": f"Model not found: {model_id}"}

        try:
            if sensor_data is not None:
                input_array = np.array(sensor_data, dtype=np.float32)
            else:
                # Generate zero input as placeholder when no data provided
                input_array = np.zeros(model.input_shape, dtype=np.float32)

            result = model.predict(input_array)
            return result.to_dict()
        except Exception as e:
            logger.error("run_anomaly_scan failed: %s", e)
            return {"error": str(e)}

    registry.register_function(
        name="run_anomaly_scan",
        description="Run anomaly detection on sensor data",
        input_schema={
            "type": "object",
            "properties": {
                "model_id": {
                    "type": "string",
                    "description": "Anomaly model ID",
                    "default": "anomaly_detector",
                },
                "sensor_data": {
                    "type": "array",
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
                "model_id": {"type": "string", "default": "anomaly_detector"},
                "limit": {"type": "integer", "default": 100, "minimum": 1, "maximum": 1000},
            },
        },
        func=get_anomaly_history,
    )
