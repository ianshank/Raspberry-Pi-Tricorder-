---
name: lint-fix
description: Run linting and type checking, fix violations
allowed-tools: Bash, Read, Edit, Grep, Glob
user-invocable: true
---

# Lint and Fix

Run all code quality checks and fix any violations.

## Steps

1. **Run ruff check:**
   ```bash
   ruff check src/ tests/
   ```

2. **Auto-fix** what ruff can handle:
   ```bash
   ruff check --fix src/ tests/
   ```

3. **Run type checking:**
   ```bash
   make typecheck-touched
   ```

4. **Review remaining issues** that couldn't be auto-fixed:
   - Read each flagged file
   - Apply manual fixes following existing code style
   - Common fixes: unused imports, missing type annotations, line length

5. **Verify** everything passes:
   ```bash
   ruff check src/ tests/
   make typecheck-touched
   ```

6. **Run tests** to confirm fixes didn't break anything:
   ```bash
   PYTHONPATH=src python -m pytest tests/ --cov=src --cov-fail-under=85 -q
   ```

7. Report a summary of what was fixed and any remaining issues that need manual review.
