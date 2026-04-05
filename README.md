# Tricorder Neural Network Platform

Edge AI sensor fusion system on Raspberry Pi 5 + Hailo-10H with LangGraph ReAct agent.

## Architecture

- **Sensors**: 10-channel ADC (ADS1263) + I2C sensors (BME680, MLX90640, AS7265x, MAX30102) + UART sensors (radar, LiDAR)
- **Neural Networks**: Anomaly detector (autoencoder-LSTM), sensor fusion transformer — designed for Hailo-10H NPU
- **Agent**: LangGraph ReAct agent with MCP tool server for autonomous sensor monitoring
- **MCP Server**: FastAPI server exposing all sensors and models as callable tools
- **Configuration**: Pydantic-based, YAML-driven, env-var overrideable — zero hardcoded values

## Quick Start

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## Project Structure

```
src/
  sensors/       # Hardware-abstracted sensor drivers (I2C/SPI/UART)
  models/        # Neural network wrappers (anomaly detection, fusion)
  agents/        # LangGraph ReAct agent
  mcp_server/    # FastAPI MCP tool server
  utils/         # Configuration and logging
tests/
  unit/          # Unit tests (mocked hardware)
  integration/   # Component integration tests
  e2e/           # End-to-end pipeline tests
  regression/    # Backwards compatibility tests
  sanity/        # Smoke tests and import validation
config/
  base.yaml      # Default configuration
```

## Configuration

All values in `config/base.yaml`. Override via environment variables:

```bash
export TRICORDER_LOGGING_LEVEL=DEBUG
```

## Testing

```bash
pytest tests/ -v                                    # All tests
pytest tests/ --cov=src --cov-report=term-missing   # With coverage
pytest tests/unit/ -v                               # Unit only
```

All tests use mocked I/O adapters — no hardware required.
