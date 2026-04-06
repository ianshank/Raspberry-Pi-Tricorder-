# Tricorder Neural Network Platform

Edge AI sensor fusion system on Raspberry Pi 5 + Hailo-10H with LangGraph ReAct agent.

## Architecture

- **Sensors**: 10-channel ADC (ADS1263) + I2C sensors (BME680, MLX90640, AS7265x, MAX30102) + UART sensors (radar, LiDAR)
- **Neural Networks**: Anomaly detector (autoencoder-LSTM), sensor fusion transformer — designed for Hailo-10H NPU
- **Agent**: LangGraph ReAct agent with MCP tool server for autonomous sensor monitoring
- **MCP Server**: FastAPI server exposing all sensors and models as callable tools
- **UI**: LCARS-inspired static dashboard with live sensor/anomaly streams and agent chat
- **Configuration**: Pydantic-based, YAML-driven, env-var overrideable — zero hardcoded values

## Quick Start

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## Project Structure

```text
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
docs/
  architecture/  # System architecture documentation (C4 model)
```

## Documentation

- C4 architecture: `docs/architecture/c4-architecture.md`
- Changelog: `CHANGELOG.md`

## Configuration

All values in `config/base.yaml`. Override via environment variables:

```bash
export TRICORDER_LOGGING_LEVEL=DEBUG
```

### UI Endpoints

- `GET /ui/index.html`: Static dashboard entrypoint
- `GET /ui/config.json`: Runtime-safe UI configuration
- `WS /ws/sensors`: Live sensor readings stream
- `WS /ws/anomalies`: Live anomaly stream
- `POST /ui/agent/chat`: Agent chat endpoint (configurable)
- `POST /ui/anomalies/ack`: Anomaly acknowledgment endpoint (configurable)

### Phase 6: Anomaly Acknowledgment Workflow

Default UI config keys:

- `ui.anomaly_ack_enabled`: Enables/disables acknowledgment endpoint and UI controls
- `ui.anomaly_ack_path`: HTTP path used by acknowledgment requests
- `ui.anomaly_ack_history_limit`: In-memory retention cap for acknowledged anomaly IDs

Anomaly stream payloads now include:

- `anomaly_id`: Stable ID used by UI and backend acknowledgment tracking
- `acknowledged`: Boolean acknowledgment state for the anomaly
- `acknowledgment`: Optional metadata when the anomaly has been acknowledged

Example acknowledgment request:

```json
{
  "anomaly_id": "anom-1234567890abcdef",
  "acknowledged_by": "ui",
  "note": "Operator acknowledged"
}
```

## Testing

```bash
pytest tests/ -v                                    # All tests
pytest tests/ -v --cov=src --cov-fail-under=85      # With coverage gate
pytest tests/unit/ -v                               # Unit only
```

All tests use mocked I/O adapters — no hardware required.

## Next Steps

1. Move anomaly acknowledgment state from in-memory retention to persistent storage (SQLite) so state survives service restarts.
2. Add UI acknowledgment history and filtering for operator audit workflows.
3. Add authenticated operator identity propagation to anomaly acknowledgment events.
4. Add CI workflow gates for `ruff`, `mypy`, and coverage-enforced `pytest`.
5. Add deployment runbooks for Raspberry Pi + Hailo operational support.

## Developed by

Ian Cruickshank
