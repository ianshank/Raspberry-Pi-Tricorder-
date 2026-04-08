"""Tests for MQTT event publishing pipeline."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_server.mqtt_publisher import (
    MQTTPublisher,
    NullMQTTPublisher,
    PahoMQTTPublisher,
    create_mqtt_publisher,
)


# ---------------------------------------------------------------------------
# NullMQTTPublisher
# ---------------------------------------------------------------------------

class TestNullMQTTPublisher:
    """NullMQTTPublisher is a no-op implementation."""

    @pytest.fixture
    def publisher(self):
        return NullMQTTPublisher()

    @pytest.mark.asyncio
    async def test_connect_returns_false(self, publisher):
        assert await publisher.connect() is False

    @pytest.mark.asyncio
    async def test_disconnect_is_noop(self, publisher):
        await publisher.disconnect()

    @pytest.mark.asyncio
    async def test_publish_returns_false(self, publisher):
        assert await publisher.publish("topic", {"key": "value"}) is False

    def test_is_connected_returns_false(self, publisher):
        assert publisher.is_connected() is False

    def test_protocol_compliance(self, publisher):
        assert isinstance(publisher, MQTTPublisher)


# ---------------------------------------------------------------------------
# PahoMQTTPublisher
# ---------------------------------------------------------------------------

class TestPahoMQTTPublisher:
    """PahoMQTTPublisher wraps paho-mqtt."""

    @pytest.fixture
    def config(self):
        return {
            "host": "test-broker",
            "port": 1883,
            "topic_prefix": "test/tricorder",
            "keepalive_s": 30,
        }

    @pytest.fixture
    def publisher(self, config):
        return PahoMQTTPublisher(config)

    def test_init_reads_config(self, publisher):
        assert publisher._host == "test-broker"
        assert publisher._port == 1883
        assert publisher._topic_prefix == "test/tricorder"
        assert publisher._keepalive_s == 30

    def test_init_defaults(self):
        pub = PahoMQTTPublisher({})
        assert pub._host == "localhost"
        assert pub._port == 1883
        assert pub._topic_prefix == "tricorder"
        assert pub._keepalive_s == 60

    def test_full_topic(self, publisher):
        assert publisher._full_topic("sensors") == "test/tricorder/sensors"
        assert publisher._full_topic("anomalies/ack") == "test/tricorder/anomalies/ack"

    def test_is_connected_initially_false(self, publisher):
        assert publisher.is_connected() is False

    def test_protocol_compliance(self, publisher):
        assert isinstance(publisher, MQTTPublisher)

    @pytest.mark.asyncio
    async def test_connect_success(self, publisher):
        mock_client = MagicMock()
        mock_client.connect = MagicMock()
        mock_client.loop_start = MagicMock()

        with patch("mcp_server.mqtt_publisher.asyncio") as mock_asyncio:
            loop = MagicMock()
            loop.run_in_executor = AsyncMock()
            mock_asyncio.get_running_loop = MagicMock(return_value=loop)

            with patch("paho.mqtt.client.Client", return_value=mock_client):
                with patch("paho.mqtt.client.CallbackAPIVersion") as mock_api:
                    mock_api.VERSION2 = 2
                    result = await publisher.connect()

        assert result is True
        assert publisher.is_connected() is True

    @pytest.mark.asyncio
    async def test_connect_import_error(self, publisher):
        with patch.dict("sys.modules", {"paho": None, "paho.mqtt": None, "paho.mqtt.client": None}):
            # Force ImportError by making the import fail
            original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

            def mock_import(name, *args, **kwargs):
                if name == "paho.mqtt.client":
                    raise ImportError("No module named 'paho'")
                return original_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=mock_import):
                result = await publisher.connect()
                assert result is False

    @pytest.mark.asyncio
    async def test_connect_failure(self, publisher):
        with patch("paho.mqtt.client.Client") as mock_cls:
            with patch("paho.mqtt.client.CallbackAPIVersion") as mock_api:
                mock_api.VERSION2 = 2
                mock_client = MagicMock()
                mock_client.connect = MagicMock(side_effect=ConnectionRefusedError("refused"))
                mock_cls.return_value = mock_client

                with patch("mcp_server.mqtt_publisher.asyncio") as mock_asyncio:
                    loop = MagicMock()
                    loop.run_in_executor = AsyncMock(side_effect=ConnectionRefusedError("refused"))
                    mock_asyncio.get_running_loop = MagicMock(return_value=loop)

                    result = await publisher.connect()
                    assert result is False
                    assert publisher.is_connected() is False

    @pytest.mark.asyncio
    async def test_disconnect(self, publisher):
        mock_client = MagicMock()
        publisher._client = mock_client
        publisher._connected = True

        await publisher.disconnect()
        mock_client.loop_stop.assert_called_once()
        mock_client.disconnect.assert_called_once()
        assert publisher.is_connected() is False

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self, publisher):
        await publisher.disconnect()  # should not raise

    @pytest.mark.asyncio
    async def test_publish_success(self, publisher):
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.rc = 0
        mock_client.publish = MagicMock(return_value=mock_result)
        publisher._client = mock_client
        publisher._connected = True

        payload = {"temperature": 22.5, "humidity": 45.0}
        result = await publisher.publish("sensors", payload)
        assert result is True

        call_args = mock_client.publish.call_args
        assert call_args[0][0] == "test/tricorder/sensors"  # uses config prefix
        published_json = json.loads(call_args[0][1])
        assert published_json["temperature"] == 22.5

    @pytest.mark.asyncio
    async def test_publish_not_connected(self, publisher):
        result = await publisher.publish("sensors", {"data": 1})
        assert result is False

    @pytest.mark.asyncio
    async def test_publish_failure(self, publisher):
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.rc = 1  # error
        mock_client.publish = MagicMock(return_value=mock_result)
        publisher._client = mock_client
        publisher._connected = True

        result = await publisher.publish("sensors", {"data": 1})
        assert result is False

    @pytest.mark.asyncio
    async def test_publish_exception(self, publisher):
        mock_client = MagicMock()
        mock_client.publish = MagicMock(side_effect=RuntimeError("publish error"))
        publisher._client = mock_client
        publisher._connected = True

        result = await publisher.publish("sensors", {"data": 1})
        assert result is False

    def test_on_connect_success(self, publisher):
        publisher._on_connect(None, None, None, MagicMock(value=0))
        assert publisher._connected is True

    def test_on_connect_failure(self, publisher):
        publisher._on_connect(None, None, None, MagicMock(value=5))
        assert publisher._connected is False

    def test_on_connect_with_int_rc(self, publisher):
        publisher._on_connect(None, None, None, 0)
        assert publisher._connected is True

    def test_on_disconnect(self, publisher):
        publisher._connected = True
        publisher._on_disconnect(None, None)
        assert publisher._connected is False


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------

class TestCreateMQTTPublisher:
    """Factory creates the right publisher type."""

    def test_creates_paho_when_enabled(self):
        pub = create_mqtt_publisher({"enabled": True, "host": "broker"}, enabled=True)
        assert isinstance(pub, PahoMQTTPublisher)

    def test_creates_null_when_feature_disabled(self):
        pub = create_mqtt_publisher({"enabled": True}, enabled=False)
        assert isinstance(pub, NullMQTTPublisher)

    def test_creates_null_when_mqtt_disabled(self):
        pub = create_mqtt_publisher({"enabled": False}, enabled=True)
        assert isinstance(pub, NullMQTTPublisher)

    def test_creates_null_when_both_disabled(self):
        pub = create_mqtt_publisher({"enabled": False}, enabled=False)
        assert isinstance(pub, NullMQTTPublisher)

    def test_default_enabled_true(self):
        pub = create_mqtt_publisher({}, enabled=True)
        assert isinstance(pub, PahoMQTTPublisher)
