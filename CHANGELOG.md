# Changelog

All notable changes to this project are documented in this file.

## [Unreleased] - 2026-04-06

### Fixed

- **Agent tool arg-passing (BUG-R2-001 / BUG-004 — HIGH)**: `execute_tools_node` was always
  calling `tool_caller(name, {})` with an empty args dict, causing every `read_sensor`
  invocation to fail. Introduced `planned_steps: List[Dict]` on `AgentState` so `evidence_gather_node`
  propagates per-tool argument dicts end-to-end through `plan_tools_node` and `execute_tools_node`.
- **Agent deduplication bug (BUG-R2-001 companion)**: `plan_tools_node` was deduplicating by
  tool name only, collapsing multiple `read_sensor` calls for different sensors to one. Dedup now
  operates on `(tool, args)` key pairs so independent sensor reads all execute.
- **Security: SHA1 flag (Bandit B324 — HIGH)**: `hashlib.sha1()` annotated with
  `usedforsecurity=False`; hash is used only for deterministic anomaly ID fingerprinting.
- **ADS1263 / bar label truncation (BUG-R2-002 — MED)**: `.bar-row` grid column changed from
  fixed `3.2rem` to `minmax(3.2rem, max-content)` so long channel names like `gas_mq135` and
  `thermocouple` render without ellipsis.
- **MLX90640 pixel count annotation (BUG-R2-003 — MED)**: Bio panel now shows
  `"SHOWING N OF 768 THERMAL PIXELS"` when the thermal frame array is shorter than the full
  768-pixel hardware frame, making the simulated subset explicit.
- **WCAG focus indicators (BUG-R2-004 — MED)**: Added `:focus-visible` outline ring
  (`2px solid #f6bd84`) globally, satisfying WCAG 2.1 SC 2.4.7 for keyboard navigation.
- **Whitespace-only query feedback (BUG-R2-005 — LOW)**: Agent chat panel now displays
  `"Query cannot be empty."` error message instead of silently discarding whitespace input.
- **WebSocket status flicker (BUG-R2-006 — LOW)**: `DataService._emitStatus` now suppresses
  `CONNECTING` transitions when the socket is already `CONNECTED`, eliminating the visible
  CONNECTING → CONNECTED → CONNECTING cycle during anomaly socket reconnects.
- **`GET /ui/anomalies/ack` 404 (BUG-R2-007 — MED)**: Added an informational `GET` handler
  alongside the existing `POST` endpoint; returns endpoint description and method hint.
- **HLK-LD2410 shared progress bar scale (BUG-R2-008 — LOW)**: MOV/STILL/DETECT bars now use
  `Math.max(...values, 600)` as a stable baseline, preventing a 1 cm reading from visually
  dominating 100% of the bar width.
- **404 routes returning bare JSON (BUG-R2-009 — LOW)**: Registered a FastAPI `exception_handler`
  for HTTP 404; returns themed HTML for `/ui/*` paths while preserving JSON detail for API paths.
- **AS7265X wavelength order (BUG-R2-010 — LOW)**: Spectral channels in `env-panel.js` are
  now sorted ascending by numeric wavelength (`parseInt`) instead of descending by intensity.
- **Chat history lost on panel re-activation (BUG-003 — MED)**: `AgentChatPanel` now overrides
  `setActive()` and calls `_restoreMessages()` when re-activated with an empty message list,
  restoring persisted sessionStorage history when navigating back to the chat panel.

### Added

- Development simulated sensors (`_SimulatedSensor`) for all 7 sensor types (bme680, mlx90640,
  as7265x, ads1263, hlk_ld2410, tfmini_s, max30102) — enables full UI without physical hardware.
- Bootstrap default tool registration (`_bootstrap_default_tools`) so the MCP server registers
  all 7 tools on startup even when no external `ToolRegistry` is injected.
- Markdown rendering in agent chat panel (`renderMarkdown`, `applyInlineMarkdown`, `escapeHtml`)
  with support for headings, bold, inline code, and bullet lists.
- sessionStorage persistence for agent chat messages (`_persistMessages`, `_restoreMessages`)
  with a 120-message cap to survive page refreshes.
- Title navigation click handler in `app.js` so clicking `TRICORDER` always returns to the
  first panel.
- `"AWAITING DATA"` placeholder label in sensor cards before the first reading arrives.
- TFMINI VALID field now renders `TRUE / FALSE / N/A` instead of a raw boolean.
- `N/A` labels for empty AS7265X spectral and ADS1263 ADC channel data.
- `GET /ui/anomalies/ack` informational endpoint.
- LCARS-themed HTML 404 response for `/ui/*` path misses.
- `.gitignore` entries for `.venv/`, `coverage.json`, `bandit.json`, and security scan outputs.
- Bootstrap tests in `test_server_coverage.py` covering default tool registration and simulated
  sensor readings (`TestDefaultToolBootstrap`).

## [Unreleased] - 2026-04-05

### Added

- LCARS-inspired web UI served by the MCP FastAPI service.
- Real-time sensor stream websocket endpoint for UI telemetry updates.
- Real-time anomaly stream websocket endpoint for alerting and status.
- Agent chat endpoint for operational Q and A with sensor context.
- Anomaly acknowledgment endpoint and UI controls for operator workflow.
- UI module sanity and unit coverage for config, API, websocket, and static assets.

### Changed

- Expanded typed configuration model with UI and anomaly acknowledgment settings.
- Updated base and test YAML configuration defaults for UI and acknowledgment behavior.
- Updated Makefile test target to enforce minimum coverage gate.
- Added websockets dependency to packaging and runtime requirements.
- Tightened type annotations across agent, sensor, and server modules.
- Hardened authentication behavior to fail closed when auth is enabled but no API key is configured.
- Sanitized user-facing error details on agent chat and websocket sensor stream paths.

