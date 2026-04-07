---
name: run-tests
description: Run the test suite with coverage reporting
argument-hint: "[test-path-or-marker]"
allowed-tools: Bash, Read, Grep, Glob
user-invocable: true
---

# Run Tests

Run the Tricorder test suite and report results.

If arguments are provided, use them as the test target:
- File path: `$ARGUMENTS` (e.g., `tests/unit/test_sensor_drivers.py`)
- Marker: `-m $ARGUMENTS` (e.g., `-m integration`)
- Keyword: `-k $ARGUMENTS` (e.g., `-k bme680`)

## Steps

1. Run tests:
   ```bash
   PYTHONPATH=src python -m pytest ${ARGUMENTS:-tests/} --cov=src --cov-fail-under=85 --cov-report=term-missing -v
   ```

2. Parse the output and report:
   - Total passed / failed / skipped / errors
   - Coverage percentage (gate: 85%)
   - For each failure: test name, file:line reference, error message

3. If tests fail, read the failing test and corresponding source file. Suggest the likely cause and a fix approach.

4. If coverage dropped below 85%, identify which modules lost coverage and suggest what tests to add.
