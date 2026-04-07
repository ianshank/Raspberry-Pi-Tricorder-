# Neural Network Models

## Dual-Path Inference

Models support two inference backends:
- **ONNX Runtime** — CPU-based, used in development and CI
- **Hailo HEF** — NPU-accelerated on Hailo-10H, used in production on RPi 5

Backend selection is automatic based on available hardware and config.

## BaseModel ABC

All models extend `BaseModel` from `base.py`. Key methods:
- `load()` — Load model weights from configured path
- `predict(input_data)` — Run inference, returns numpy array
- `validate_model_input(data)` — Shape/type validation before inference

Input/output shapes are defined in config and validated at load time.

## ModelRegistry

`ModelRegistry` manages model instances. Use `register()`, `get()`, `clear()`. The registry is instance-based — created in `create_app()` and passed via closures.

## Current Models

- `anomaly_detector.py` — Autoencoder-LSTM, input [1, 256, 10], output [1, 10]. Window-based anomaly scoring.
- `fusion_engine.py` — Transformer-based sensor fusion, input [1, 16, 64], output [1, 512]. Multi-sensor evidence integration.

## Performance Logging

Inference calls that exceed 100ms trigger a warning log. This threshold is checked in the `predict()` path.

## Config

Model config lives under `models:` in `config/base.yaml` with paths, shapes, confidence thresholds, and quantization settings.
