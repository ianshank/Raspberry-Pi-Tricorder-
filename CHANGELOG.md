# Changelog

All notable changes to this project are documented in this file.

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

