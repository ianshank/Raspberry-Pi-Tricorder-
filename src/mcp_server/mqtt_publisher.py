"""MQTT event publishing for Tricorder Neural Platform.

Publishes sensor readings, anomaly events, agent reports, and ACK events
to an MQTT broker. All topic names derive from config — no hardcoded values.

Uses Protocol-based DI so the server can inject a NullMQTTPublisher when
MQTT is disabled.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Protocol, runtime_checkable


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class MQTTPublisher(Protocol):
    """Async interface for MQTT event publishing."""

    async def connect(self) -> bool:
        """Connect to the MQTT broker. Returns True on success."""
        ...

    async def disconnect(self) -> None:
        """Disconnect from the broker gracefully."""
        ...

    async def publish(self, topic: str, payload: Dict[str, Any]) -> bool:
        """Publish a JSON payload to a topic. Returns True on success."""
        ...

    def is_connected(self) -> bool:
        """Return True if the client is currently connected."""
        ...


# ---------------------------------------------------------------------------
# Paho MQTT implementation
# ---------------------------------------------------------------------------

class PahoMQTTPublisher:
    """MQTT publisher backed by ``paho.mqtt.client``.

    Reads all connection parameters from the provided config dict,
    which mirrors the ``MQTTConfig`` Pydantic model fields.
    """

    DEFAULT_RECONNECT_DELAY_S = 5.0
    DEFAULT_MAX_RECONNECT_DELAY_S = 60.0

    def __init__(self, config: Dict[str, Any]) -> None:
        self._host = str(config.get("host", "localhost"))
        self._port = int(config.get("port", 1883))
        self._topic_prefix = str(config.get("topic_prefix", "tricorder"))
        self._keepalive_s = int(config.get("keepalive_s", 60))
        self._reconnect_delay_s = float(
            config.get("reconnect_delay_s", self.DEFAULT_RECONNECT_DELAY_S)
        )
        self._max_reconnect_delay_s = float(
            config.get("max_reconnect_delay_s", self.DEFAULT_MAX_RECONNECT_DELAY_S)
        )
        self._connected = False
        self._client: Any = None
        logger.info(
            "PahoMQTTPublisher created: host=%s, port=%d, prefix=%s",
            self._host,
            self._port,
            self._topic_prefix,
        )

    def _full_topic(self, suffix: str) -> str:
        """Build full topic path from prefix and suffix."""
        return f"{self._topic_prefix}/{suffix}"

    async def connect(self) -> bool:
        try:
            import paho.mqtt.client as mqtt  # type: ignore[import-untyped]
        except ImportError:
            logger.warning("paho-mqtt is not installed; MQTT publishing disabled")
            return False

        try:
            self._client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            )
            self._client.on_connect = self._on_connect
            self._client.on_disconnect = self._on_disconnect

            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: self._client.connect(
                    self._host,
                    self._port,
                    keepalive=self._keepalive_s,
                ),
            )
            self._client.loop_start()
            self._connected = True
            logger.info(
                "MQTT connected to %s:%d", self._host, self._port,
            )
            return True
        except Exception as exc:
            logger.warning("MQTT connect failed: %s", exc)
            self._connected = False
            return False

    def _on_connect(self, client: Any, userdata: Any, flags: Any, rc: Any, properties: Any = None) -> None:
        if hasattr(rc, 'value'):
            rc_val = rc.value
        else:
            rc_val = int(rc)
        if rc_val == 0:
            self._connected = True
            logger.debug("MQTT on_connect: success")
        else:
            self._connected = False
            logger.warning("MQTT on_connect: rc=%s", rc)

    def _on_disconnect(self, client: Any, userdata: Any, flags: Any = None, rc: Any = None, properties: Any = None) -> None:
        self._connected = False
        logger.info("MQTT disconnected (rc=%s)", rc)

    async def disconnect(self) -> None:
        if self._client is not None:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception as exc:
                logger.warning("MQTT disconnect error: %s", exc)
            finally:
                self._connected = False
                logger.info("MQTT publisher disconnected")

    async def publish(self, topic: str, payload: Dict[str, Any]) -> bool:
        if not self._connected or self._client is None:
            logger.debug("MQTT publish skipped (not connected): topic=%s", topic)
            return False

        full_topic = self._full_topic(topic)
        try:
            message = json.dumps(payload, default=str)
            result = self._client.publish(full_topic, message, qos=1)
            if result.rc == 0:
                logger.debug("MQTT published: topic=%s, size=%d", full_topic, len(message))
                return True
            logger.warning("MQTT publish failed: topic=%s, rc=%s", full_topic, result.rc)
            return False
        except Exception as exc:
            logger.warning("MQTT publish error: topic=%s, err=%s", full_topic, exc)
            return False

    def is_connected(self) -> bool:
        return self._connected


# ---------------------------------------------------------------------------
# Null implementation (disabled MQTT)
# ---------------------------------------------------------------------------

class NullMQTTPublisher:
    """No-op publisher for when MQTT is disabled."""

    async def connect(self) -> bool:
        return False

    async def disconnect(self) -> None:
        pass

    async def publish(self, topic: str, payload: Dict[str, Any]) -> bool:
        return False

    def is_connected(self) -> bool:
        return False


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_mqtt_publisher(
    mqtt_config: Dict[str, Any],
    enabled: bool = True,
) -> MQTTPublisher:
    """Create the appropriate MQTT publisher based on config.

    Parameters
    ----------
    mqtt_config:
        Dict mirroring ``MQTTConfig`` fields.
    enabled:
        Whether MQTT publishing is enabled (from feature flags).
    """
    mqtt_enabled = bool(mqtt_config.get("enabled", True))
    if not enabled or not mqtt_enabled:
        logger.info("MQTT publishing disabled")
        return NullMQTTPublisher()

    return PahoMQTTPublisher(mqtt_config)
