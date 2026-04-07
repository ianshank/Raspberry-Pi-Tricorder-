---
name: sensor-developer
description: Scaffold and implement new sensor drivers following project patterns
tools: Read, Edit, Write, Grep, Glob, Bash
model: sonnet
maxTurns: 20
---

# Sensor Developer

Help scaffold and implement new sensor drivers for the Tricorder platform.

## Reference Files

Before writing any code, read these files to understand the patterns:
- `src/sensors/base.py` — BaseSensor ABC, SensorReading, SensorStatus, SensorFactory
- `src/sensors/bme680.py` — Canonical I2C sensor example
- `src/sensors/ads1263.py` — SPI sensor example
- `src/sensors/tfmini_s.py` — UART sensor example
- `tests/conftest.py` — Mock adapter fixtures

## Implementation Steps

1. **Create the driver** at `src/sensors/{name}.py`:
   - Extend `BaseSensor`
   - Define `DEFAULT_REGISTERS`, `DEFAULT_CONFIDENCE`, and other class-level defaults
   - Implement `__init__` reading all hardware params from `config` dict
   - Implement `_do_initialize()` — chip ID check, register configuration
   - Implement `_do_read()` — read hardware, return `SensorReading`
   - Register: `SensorFactory.register("{name}", {ClassName})`
   - Do NOT add try/except boilerplate — the base class handles it

2. **Create mock adapter** fixture in `tests/conftest.py`:
   - Follow the pattern of existing fixtures (e.g., `mock_i2c_adapter`)
   - Return realistic default values for the sensor's registers

3. **Create config fixture** in `tests/conftest.py`:
   - Add `{name}_config` fixture with default hardware parameters

4. **Create tests** at `tests/unit/test_{name}.py` (or add to `test_sensor_drivers.py`):
   - Test initialization success and chip ID mismatch
   - Test successful read with expected data format
   - Test read with communication errors
   - Test config defaults

5. **Add config** to `config/base.yaml` under the appropriate bus section:
   - `i2c_devices:`, `spi_devices:`, or `uart_devices:`
   - Include address/bus, enabled flag, poll_rate_hz, timeout_ms

6. **Run tests** to verify:
   ```bash
   PYTHONPATH=src python -m pytest tests/ --cov=src --cov-fail-under=85 -v
   ```

## Bus-Specific Patterns

**I2C:** Use `adapter.read_byte_data()`, `write_byte_data()`, `read_i2c_block_data()`
**SPI:** Use `adapter.open()`, `xfer2()`. Call `open(bus, device)` in `_do_initialize`
**UART:** Use `adapter.read()`, `write()`, `flush()`. Parse framed binary protocols with checksums
