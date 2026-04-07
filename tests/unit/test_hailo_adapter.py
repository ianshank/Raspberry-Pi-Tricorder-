"""Unit tests for HailoRT inference adapter."""

import numpy as np

from models.base import InferenceAdapter
from models.hailo_adapter import HailoAdapter


class TestHailoAdapterDefaults:
    """Constructor default values."""

    def test_default_device_id(self):
        adapter = HailoAdapter()
        assert adapter._device_id == 0

    def test_default_hef_path_is_none(self):
        adapter = HailoAdapter()
        assert adapter._hef_path is None

    def test_custom_device_id(self):
        adapter = HailoAdapter(device_id=2)
        assert adapter._device_id == 2

    def test_custom_hef_path(self):
        adapter = HailoAdapter(hef_path="/opt/models/model.hef")
        assert adapter._hef_path == "/opt/models/model.hef"

    def test_not_loaded_by_default(self):
        adapter = HailoAdapter()
        assert adapter._loaded is False


class TestHailoAdapterLoad:
    """Loading behaviour (ImportError / stub path)."""

    def test_load_returns_false_without_hailort(self):
        adapter = HailoAdapter()
        result = adapter.load("nonexistent.hef")
        assert result is False

    def test_remains_unloaded_after_import_error(self):
        adapter = HailoAdapter()
        adapter.load("nonexistent.hef")
        assert adapter._loaded is False


class TestHailoAdapterPredict:
    """Prediction when the model is not loaded."""

    def test_predict_returns_zeros_when_not_loaded(self):
        adapter = HailoAdapter()
        input_data = np.ones((1, 10), dtype=np.float32)
        output = adapter.predict(input_data)
        np.testing.assert_array_equal(output, np.zeros((1, 10), dtype=np.float32))

    def test_predict_preserves_shape(self):
        adapter = HailoAdapter()
        input_data = np.random.randn(4, 8, 16).astype(np.float32)
        output = adapter.predict(input_data)
        assert output.shape == (4, 8, 16)

    def test_predict_preserves_dtype(self):
        adapter = HailoAdapter()
        input_data = np.ones((2, 3), dtype=np.float64)
        output = adapter.predict(input_data)
        assert output.dtype == np.float64


class TestHailoAdapterGetInfo:
    """get_info() dictionary structure."""

    def test_get_info_keys(self):
        adapter = HailoAdapter()
        info = adapter.get_info()
        assert set(info.keys()) == {"backend", "device_id", "hef_path", "loaded"}

    def test_get_info_backend(self):
        adapter = HailoAdapter()
        info = adapter.get_info()
        assert info["backend"] == "hailort"

    def test_get_info_reflects_constructor_args(self):
        adapter = HailoAdapter(device_id=3, hef_path="/tmp/test.hef")
        info = adapter.get_info()
        assert info["device_id"] == 3
        assert info["hef_path"] == "/tmp/test.hef"

    def test_get_info_loaded_false_by_default(self):
        adapter = HailoAdapter()
        info = adapter.get_info()
        assert info["loaded"] is False


class TestHailoAdapterProtocol:
    """Protocol conformance."""

    def test_isinstance_inference_adapter(self):
        adapter = HailoAdapter()
        assert isinstance(adapter, InferenceAdapter)
