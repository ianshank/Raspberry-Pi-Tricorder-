---
name: add-sensor
description: Scaffold a new sensor driver with tests and config
argument-hint: "[sensor-name] [bus-type: i2c|spi|uart]"
allowed-tools: Read, Edit, Write, Grep, Glob, Bash
user-invocable: true
---

# Add Sensor Driver

Scaffold a complete new sensor driver for the Tricorder platform.

**Arguments:** `$ARGUMENTS` should be `<sensor-name> <bus-type>` (e.g., `bmp390 i2c`)

## Steps

1. **Read the canonical example** for the bus type:
   - I2C: `src/sensors/bme680.py`
   - SPI: `src/sensors/ads1263.py`
   - UART: `src/sensors/tfmini_s.py`

2. **Read the base class** at `src/sensors/base.py` for `BaseSensor`, `SensorReading`, `SensorFactory`.

3. **Create the driver** at `src/sensors/<sensor-name>.py`:
   - Class inheriting from `BaseSensor`
   - `DEFAULT_REGISTERS` and `DEFAULT_CONFIDENCE` class constants
   - `__init__` pulling all hardware params from `config` dict
   - `_do_initialize()` with chip ID verification and register setup
   - `_do_read()` returning a `SensorReading`
   - `SensorFactory.register("<sensor-name>", <ClassName>)` at module bottom
   - No try/except boilerplate — base class handles it

4. **Add mock fixture** to `tests/conftest.py`:
   - Mock adapter fixture matching the bus type pattern
   - Config fixture with default hardware parameters

5. **Create tests** at `tests/unit/test_<sensor-name>.py`:
   - Test successful initialization
   - Test chip ID mismatch raises `SensorInitializationError`
   - Test successful read returns expected data structure
   - Test communication error handling

6. **Add config** to `config/base.yaml` under the appropriate bus section (`i2c_devices`, `spi_devices`, or `uart_devices`).

7. **Run the full test suite** to verify:
   ```bash
   PYTHONPATH=src python -m pytest tests/ --cov=src --cov-fail-under=85 -v
   ```

8. **Run lint** to verify:
   ```bash
   ruff check src/ tests/
   ```
