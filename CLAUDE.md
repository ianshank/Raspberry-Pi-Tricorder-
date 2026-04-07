# Raspberry Pi Tricorder

Neural network-enhanced sensor fusion platform on Raspberry Pi 5 + Hailo-10H NPU.

## Commands

```bash
# Install
pip install -e ".[dev,agent]"

# Test (all, with 85% coverage gate)
PYTHONPATH=src python -m pytest tests/ --cov=src --cov-fail-under=85 -v

# Test (unit only)
PYTHONPATH=src python -m pytest tests/unit/ -v

# Test (single file)
PYTHONPATH=src python -m pytest tests/unit/test_bme680.py -v

# Lint
ruff check src/ tests/

# Type check
make typecheck-touched

# Run MCP server
PYTHONPATH=src python -m uvicorn mcp_server.server:app --reload

# Clean
make clean
```

**PYTHONPATH=src is required** for all pytest and python commands.

## Architecture

```
src/
  sensors/       7 hardware drivers (I2C, SPI, UART) + base + manager
  models/        ONNX/Hailo neural networks (anomaly detector, fusion engine)
  mcp_server/    FastAPI server, tool registry, WebSocket streaming
  agents/        LangGraph ReAct agent (5-node state machine)
  utils/         Pydantic config, shared constants, structlog logging
  ui/            LCARS-inspired web dashboard (HTML/CSS/ES Modules)
```

**Entry points:** `tricorder-mcp` (MCP server), `tricorder-agent` (LangGraph agent)

**Config system:** `config/base.yaml` + env var overrides with `TRICORDER__` prefix. Nested paths use double underscore: `TRICORDER__LOGGING__LEVEL=DEBUG`. All config flows through Pydantic models in `src/utils/config.py`.

## Code Style

- **Config-driven:** All hardware addresses, register maps, thresholds, and tuning parameters come from config dicts. Never hardcode I2C addresses, SPI bus numbers, or UART ports.
- **Pydantic for validation:** Use Pydantic BaseModel for request/response schemas and config validation. See `src/utils/config.py`.
- **structlog for logging:** Use `logging.getLogger(__name__)` in each module. structlog is configured globally in `src/utils/logging_setup.py`. Use DEBUG for entry/exit, INFO for milestones, WARNING for degraded state, ERROR for failures.
- **Protocol-based DI:** Hardware adapters are injected via constructor, not imported. This enables mock-based testing without real hardware. See adapter protocols in `src/sensors/base.py`.
- **Template Method pattern:** Sensor drivers implement `_do_initialize()` and `_do_read()`. The base class `BaseSensor` handles try/except, status tracking, and error recording. Never add boilerplate error handling in drivers.
- **Registry pattern:** `SensorFactory.register()` for sensor types, `_SIMULATION_REGISTRY` for simulated values, `ToolRegistry` for MCP tools. Register at module bottom.
- **Shared constants:** Import from `src/utils/constants.py`. Never duplicate severity thresholds, sensor group names, or query limits inline.

## Testing

- **85% coverage gate** enforced in CI (currently ~96%)
- **Markers:** `@pytest.mark.integration`, `@pytest.mark.e2e`, `@pytest.mark.regression`, `@pytest.mark.sanity`, `@pytest.mark.hardware` (skipped in CI), `@pytest.mark.slow`
- **Mock adapters:** Always use fixtures from `tests/conftest.py` (`mock_i2c_adapter`, `mock_spi_adapter`, `mock_uart_adapter`, etc.). Never create inline mocks for hardware.
- **Test file naming:** mirrors source — `src/sensors/bme680.py` -> `tests/unit/test_sensor_drivers.py`
- **Config fixtures:** `bme680_config`, `ads1263_config`, etc. in conftest.py

## Git Workflow

- Create feature branches from main, never commit directly to main
- Run `PYTHONPATH=src python -m pytest tests/ --cov=src --cov-fail-under=85 -q` before committing
- Run `ruff check src/ tests/` before pushing

## Critical Rules

1. Never commit `.env` files or secrets — use `.env.example` as template
2. Never hardcode hardware addresses — all values from config
3. Never add try/except boilerplate in sensor `_do_initialize`/`_do_read` — base class handles it
4. Never duplicate constants — import from `src/utils/constants.py`
5. Always add tests for new code — match the existing test patterns in `tests/`
6. Always set `PYTHONPATH=src` for any Python/pytest command

## Key Files

- `src/sensors/base.py` — BaseSensor ABC, SensorReading, SensorStatus, SensorFactory
- `src/mcp_server/server.py` — FastAPI app, create_app(), ToolRegistry, WebSocket handlers
- `src/agents/langgraph_agent.py` — TricorderAgent, ReAct graph nodes
- `src/models/base.py` — BaseModel ABC, ModelRegistry, ONNX/Hailo inference
- `src/utils/config.py` — TricorderConfig Pydantic model, YAML + env var loading
- `src/utils/constants.py` — Shared constants (severity thresholds, sensor groups)
- `tests/conftest.py` — All mock adapters and config fixtures
- `config/base.yaml` — Primary configuration file

## CI

GitHub Actions (`.github/workflows/ci.yml`): lint (ruff) -> typecheck (mypy) -> test (pytest, Python 3.11 + 3.12, 85% coverage gate). Triggers on push to main and `claude/**` branches.
