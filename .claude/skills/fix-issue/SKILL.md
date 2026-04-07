---
name: fix-issue
description: Diagnose and fix a GitHub issue
argument-hint: "[issue-number]"
allowed-tools: Bash, Read, Edit, Write, Grep, Glob
user-invocable: true
---

# Fix Issue

Diagnose and fix a GitHub issue for the Tricorder project.

**Arguments:** `$ARGUMENTS` is the issue number (e.g., `42`)

## Steps

1. **Get issue details:** Read the issue description and any comments to understand the bug or feature request.

2. **Search the codebase** for relevant code:
   - Use Grep to find keywords mentioned in the issue
   - Use Glob to locate related files
   - Read the identified files to understand the current behavior

3. **Reproduce** (if applicable):
   - Write or identify a test that demonstrates the bug
   - Run it to confirm: `PYTHONPATH=src python -m pytest <test-file> -v`

4. **Implement the fix:**
   - Make minimal, targeted changes
   - Follow existing patterns in the codebase
   - Do not refactor unrelated code

5. **Write or update tests:**
   - Add a test that would have caught this bug
   - Ensure the test passes with the fix
   - Follow test patterns in `tests/conftest.py` for fixtures

6. **Verify:**
   ```bash
   PYTHONPATH=src python -m pytest tests/ --cov=src --cov-fail-under=85 -v
   ruff check src/ tests/
   ```

7. **Commit** with a message referencing the issue:
   ```
   fix: <description> (fixes #<issue-number>)
   ```
