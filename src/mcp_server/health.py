"""Health and metrics endpoints for Tricorder Neural Platform.

Provides liveness (``/health``) and detailed system health (``/health/detailed``)
endpoints. The basic ``/health`` response is backwards-compatible with the
original inline handler.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)


def build_basic_health(
    tools_registered: int,
) -> Dict[str, Any]:
    """Build the basic liveness response (backwards-compatible shape)."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tools_registered": tools_registered,
    }


def build_detailed_health(
    *,
    version: str,
    start_time: float,
    tools_registered: int,
    sensor_health: Dict[str, Dict[str, Any]],
    mqtt_connected: bool,
    mqtt_messages_published: int = 0,
) -> Dict[str, Any]:
    """Build the detailed health response with per-sensor status.

    Parameters
    ----------
    version:
        Project version string from config.
    start_time:
        ``time.monotonic()`` value captured at server startup.
    tools_registered:
        Number of tools in the ToolRegistry.
    sensor_health:
        Per-sensor health dict from ``SensorManager.get_health_summary()``.
    mqtt_connected:
        Whether the MQTT publisher is currently connected.
    mqtt_messages_published:
        Count of MQTT messages published since startup.
    """
    uptime_s = round(time.monotonic() - start_time, 1)

    # Derive overall status from sensor health
    if not sensor_health:
        overall = "healthy"
    else:
        statuses = [s.get("status", "unknown") for s in sensor_health.values()]
        error_count = sum(1 for s in statuses if s in ("error", "uninitialized"))
        ready_count = sum(1 for s in statuses if s in ("ready", "reading"))

        if ready_count == 0 and len(sensor_health) > 0:
            overall = "unhealthy"
        elif error_count > 0:
            overall = "degraded"
        else:
            overall = "healthy"

    result = {
        "status": overall,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": version,
        "uptime_s": uptime_s,
        "tools_registered": tools_registered,
        "sensors": sensor_health,
        "mqtt": {
            "connected": mqtt_connected,
            "messages_published": mqtt_messages_published,
        },
    }
    logger.debug(
        "Detailed health: status=%s, sensors=%d, uptime=%.1fs",
        overall,
        len(sensor_health),
        uptime_s,
    )
    return result
