"""Unit tests for neural network model framework."""

import pytest
from unittest.mock import Mock
import numpy as np

from models.base import (
    ModelStatus, ModelResult, BaseModel, ModelRegistry,
    ModelError, ModelLoadError, ModelInferenceError,
)
from models.anomaly_detector import AnomalyDetector
from models.fusion_engine import FusionEngine


class TestModelResult:
    def test_to_dict(self):
        result = ModelResult(
            output={"score": 0.8},
            confidence=0.9,
            inference_time_ms=5.0,
        )
        d = result.to_dict()
        assert d["confidence"] == 0.9
        assert d["inference_time_ms"] == 5.0

    def test_to_dict_numpy(self):
        result = ModelResult(output=np.array([1.0, 2.0, 3.0]))
        d = result.to_dict()
        assert d["output"] == [1.0, 2.0, 3.0]


class TestModelStatus:
    def test_all_statuses(self):
        assert ModelStatus.UNLOADED.value == "unloaded"
        assert ModelStatus.LOADED.value == "loaded"
        assert ModelStatus.RUNNING.value == "running"
        assert ModelStatus.ERROR.value == "error"


class TestModelExceptions:
    def test_hierarchy(self):
        assert issubclass(ModelLoadError, ModelError)
        assert issubclass(ModelInferenceError, ModelError)


class TestAnomalyDetector:
    def test_load_success(self, mock_inference_adapter, anomaly_model_config):
        model = AnomalyDetector("ad_01", mock_inference_adapter, anomaly_model_config)
        assert model.load() is True
        assert model.status == ModelStatus.LOADED

    def test_load_failure(self, mock_inference_adapter, anomaly_model_config):
        mock_inference_adapter.load.return_value = False
        model = AnomalyDetector("ad_01", mock_inference_adapter, anomaly_model_config)
        with pytest.raises(ModelLoadError):
            model.load()

    def test_predict(self, mock_inference_adapter, anomaly_model_config):
        model = AnomalyDetector("ad_01", mock_inference_adapter, anomaly_model_config)
        model.load()
        input_data = np.random.randn(1, 256, 10).astype(np.float32)
        result = model.predict(input_data)
        assert "anomaly_score" in result.output
        assert "is_anomaly" in result.output
        assert result.inference_time_ms >= 0

    def test_predict_shape_mismatch(self, mock_inference_adapter, anomaly_model_config):
        model = AnomalyDetector("ad_01", mock_inference_adapter, anomaly_model_config)
        model.load()
        bad_input = np.zeros((1, 10, 5))
        with pytest.raises(ModelInferenceError, match="Input shape mismatch"):
            model.predict(bad_input)

    def test_predict_reshapable(self, mock_inference_adapter, anomaly_model_config):
        """Test that input with correct total elements but wrong shape gets reshaped."""
        model = AnomalyDetector("ad_01", mock_inference_adapter, anomaly_model_config)
        model.load()
        # Same total elements, different shape
        input_data = np.random.randn(2560).astype(np.float32)
        result = model.predict(input_data)
        assert "anomaly_score" in result.output

    def test_set_baseline(self, mock_inference_adapter, anomaly_model_config):
        model = AnomalyDetector("ad_01", mock_inference_adapter, anomaly_model_config)
        model.load()
        baseline = np.random.randn(1, 256, 10).astype(np.float32)
        model.set_baseline(baseline)
        assert model._baseline_mse > 0

    def test_anomaly_history(self, mock_inference_adapter, anomaly_model_config):
        model = AnomalyDetector("ad_01", mock_inference_adapter, anomaly_model_config)
        model.load()
        for _ in range(5):
            input_data = np.random.randn(1, 256, 10).astype(np.float32)
            model.predict(input_data)
        history = model.get_anomaly_history(limit=3)
        assert len(history) <= 3

    def test_get_info(self, mock_inference_adapter, anomaly_model_config):
        model = AnomalyDetector("ad_01", mock_inference_adapter, anomaly_model_config)
        model.load()
        info = model.get_info()
        assert info["model_id"] == "ad_01"
        assert info["status"] == "loaded"


class TestFusionEngine:
    def test_load_success(self, mock_inference_adapter, fusion_model_config):
        model = FusionEngine("fusion_01", mock_inference_adapter, fusion_model_config)
        assert model.load() is True

    def test_load_failure(self, mock_inference_adapter, fusion_model_config):
        mock_inference_adapter.load.return_value = False
        model = FusionEngine("fusion_01", mock_inference_adapter, fusion_model_config)
        with pytest.raises(ModelLoadError):
            model.load()

    def test_predict(self, mock_inference_adapter, fusion_model_config):
        model = FusionEngine("fusion_01", mock_inference_adapter, fusion_model_config)
        model.load()
        input_data = np.random.randn(1, 16, 64).astype(np.float32)
        result = model.predict(input_data)
        assert "scene_embedding" in result.output
        assert "embedding_norm" in result.output

    def test_predict_shape_mismatch(self, mock_inference_adapter, fusion_model_config):
        model = FusionEngine("fusion_01", mock_inference_adapter, fusion_model_config)
        model.load()
        bad_input = np.zeros((1, 5, 5))
        with pytest.raises(ModelInferenceError, match="Input shape mismatch"):
            model.predict(bad_input)

    def test_fuse_sensor_readings(self, mock_inference_adapter, fusion_model_config):
        model = FusionEngine("fusion_01", mock_inference_adapter, fusion_model_config)
        model.load()
        embeddings = {
            "sensor_a": np.random.randn(1, 64).astype(np.float32),
            "sensor_b": np.random.randn(1, 64).astype(np.float32),
        }
        result = model.fuse_sensor_readings(embeddings)
        assert "scene_embedding" in result.output

    def test_fuse_empty(self, mock_inference_adapter, fusion_model_config):
        model = FusionEngine("fusion_01", mock_inference_adapter, fusion_model_config)
        model.load()
        with pytest.raises(ModelInferenceError, match="No sensor embeddings"):
            model.fuse_sensor_readings({})

    def test_get_info(self, mock_inference_adapter, fusion_model_config):
        model = FusionEngine("fusion_01", mock_inference_adapter, fusion_model_config)
        info = model.get_info()
        assert info["model_id"] == "fusion_01"
        assert info["status"] == "unloaded"


class TestModelRegistry:
    def setup_method(self):
        self._orig_registry = ModelRegistry._registry.copy()
        self._orig_instances = ModelRegistry._instances.copy()

    def teardown_method(self):
        ModelRegistry._registry = self._orig_registry
        ModelRegistry._instances = self._orig_instances

    def test_register_and_create(self):
        adapter = Mock()
        adapter.load = Mock(return_value=True)
        adapter.predict = Mock(return_value=np.zeros(10))
        model = ModelRegistry.create(
            "anomaly_detector", "test_ad", adapter,
            {"model_path": "test.onnx", "input_shape": [1, 256, 10], "output_shape": [1, 10]}
        )
        assert isinstance(model, AnomalyDetector)

    def test_create_unknown(self):
        with pytest.raises(ValueError, match="Unknown model type"):
            ModelRegistry.create("nonexistent", "t", Mock(), {})

    def test_get_instance(self):
        adapter = Mock()
        adapter.load = Mock(return_value=True)
        ModelRegistry.create(
            "anomaly_detector", "inst_01", adapter,
            {"model_path": "test.onnx", "input_shape": [1, 256, 10], "output_shape": [1, 10]}
        )
        assert ModelRegistry.get("inst_01") is not None
        assert ModelRegistry.get("nonexistent") is None

    def test_list_types(self):
        types = ModelRegistry.list_types()
        assert "anomaly_detector" in types
        assert "fusion_transformer" in types
