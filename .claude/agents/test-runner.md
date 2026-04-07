---
name: test-runner
description: Run the test suite and report results with failure analysis
tools: Bash, Read, Grep, Glob
disallowedTools: Edit, Write
model: sonnet
maxTurns: 10
isolation: worktree
---

# Test Runner

Run the Tricorder test suite in an isolated worktree and report results.

## Instructions

1. Run the full test suite:
   ```bash
   PYTHONPATH=src python -m pytest tests/ --cov=src --cov-fail-under=85 --cov-report=term-missing -v
   ```

2. If specific tests or markers were requested via arguments, adjust the command:
   - Single file: `PYTHONPATH=src python -m pytest tests/unit/test_sensor_drivers.py -v`
   - By marker: `PYTHONPATH=src python -m pytest tests/ -m integration -v`
   - By keyword: `PYTHONPATH=src python -m pytest tests/ -k "bme680" -v`

3. Analyze the output:
   - Count passed, failed, skipped, errors
   - For each failure, report the test name, file:line, and the assertion/error message
   - Check coverage percentage against the 85% gate
   - Identify any modules below 80% coverage

4. Report a summary in this format:
   ```
   Results: X passed, Y failed, Z skipped
   Coverage: XX% (gate: 85%)
   Low coverage: [list modules below 80%]
   Failures: [list with file:line and short description]
   ```

5. If there are failures, read the relevant source files to suggest likely root causes.
