# Sensor Drivers

## Template Method Pattern

All sensor drivers extend `BaseSensor` from `base.py`. Implement only:

- `_do_initialize(self) -> bool` — Hardware setup (chip ID check, register config). Return True on success, raise `SensorInitializationError` for ID mismatches.
- `_do_read(self) -> SensorReading` — Read hardware, return `SensorReading`. Raise `SensorCommunicationError` for invalid data.

**Do NOT:**
- Add try/except around `_do_initialize` or `_do_read` — the base class wraps both with error recording, status tracking, and exception translation
- Set `self.status` manually (except in `calibrate()` or `reset()` methods)
- Call `self._record_reading()` or `self._record_error()` — the template handles this

## Registration

Register at module bottom: `SensorFactory.register("sensor_name", SensorClass)`

## Config-Driven Design

All hardware parameters come from the `config` dict passed to `__init__`:
```python
self.address = config.get("address", 0x76)       # I2C address
self.registers = config.get("registers", self.DEFAULT_REGISTERS)
```

Define class-level `DEFAULT_*` constants for fallbacks. Never hardcode addresses or register values in methods.

## Adapter Protocols

Drivers receive an injected `adapter` (not imported). Adapter methods by bus type:

**I2C:** `read_byte_data(addr, reg)`, `write_byte_data(addr, reg, val)`, `read_i2c_block_data(addr, reg, length)`, `write_i2c_block_data(addr, reg, data)`
**SPI:** `open(bus, device)`, `xfer2(data)`, `close()`
**UART:** `read(size)`, `write(data)`, `flush()`, `readline()`

## Canonical Example

`bme680.py` — I2C environmental sensor. Follow this pattern for new drivers.

## Testing

Mock adapters are in `tests/conftest.py`. Each sensor type has a fixture (`mock_i2c_adapter`, `mock_spi_adapter`, `mock_uart_adapter`) plus sensor-specific variants (`mock_i2c_mlx90640`, `mock_uart_tfmini`).
