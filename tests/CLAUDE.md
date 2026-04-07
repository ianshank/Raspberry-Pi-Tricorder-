# Testing

## Commands

```bash
# Full suite with coverage
PYTHONPATH=src python -m pytest tests/ --cov=src --cov-fail-under=85 -v

# Unit tests only
PYTHONPATH=src python -m pytest tests/unit/ -v

# Integration tests
PYTHONPATH=src python -m pytest tests/integration/ -v -m integration

# Single file
PYTHONPATH=src python -m pytest tests/unit/test_sensor_drivers.py -v

# Single test
PYTHONPATH=src python -m pytest tests/unit/test_sensor_drivers.py::TestBME680 -v

# With coverage report
PYTHONPATH=src python -m pytest tests/ --cov=src --cov-fail-under=85 --cov-report=term-missing --cov-report=html -v
```

**PYTHONPATH=src is always required.**

## Test Categories

| Directory | Marker | Purpose |
|---|---|---|
| `unit/` | (none) | Individual module tests |
| `integration/` | `@pytest.mark.integration` | Component interaction |
| `e2e/` | `@pytest.mark.e2e` | Full pipeline |
| `regression/` | `@pytest.mark.regression` | Backwards compatibility |
| `sanity/` | `@pytest.mark.sanity` | Smoke tests, import checks |

Additional markers: `@pytest.mark.hardware` (skipped in CI), `@pytest.mark.slow` (>1s)

## Fixtures

All shared fixtures live in `conftest.py`. Key fixtures:

**Mock Adapters:** `mock_i2c_adapter`, `mock_i2c_mlx90640`, `mock_i2c_as7265x`, `mock_i2c_max30102`, `mock_spi_adapter`, `mock_uart_adapter`, `mock_uart_tfmini`, `mock_inference_adapter`

**Config:** `bme680_config`, `mlx90640_config`, `as7265x_config`, `max30102_config`, `ads1263_config`, `hlk_ld2410_config`, `tfmini_config`, `agent_config`, `anomaly_model_config`, `fusion_model_config`

**Data:** `sample_sensor_reading`, `test_config_path`

Always use these fixtures. Never create inline mocks for hardware adapters.

## Conventions

- Test file mirrors source: `sensors/bme680.py` -> `unit/test_sensor_drivers.py`
- Class naming: `TestBME680`, `TestADS1263`, `TestTricorderAgent`
- Use `pytest.raises(ExceptionType, match="pattern")` for error assertions
- Use `pytest.mark.parametrize` for data-driven tests
- Coverage: 85% CI gate, currently ~96%. New code must maintain this.
