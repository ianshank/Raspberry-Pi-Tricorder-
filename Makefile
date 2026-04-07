.PHONY: help install test test-unit test-integration test-hardware test-coverage lint typecheck-touched clean run-mcp

help:
	@echo "Available targets:"
	@echo "  install         - Install dependencies"
	@echo "  test            - Run all tests"
	@echo "  test-unit       - Run unit tests only"
	@echo "  test-integration- Run integration tests"
	@echo "  test-coverage   - Run tests with coverage report"
	@echo "  lint            - Run linters"
	@echo "  typecheck-touched - Run mypy on touched modules"
	@echo "  clean           - Remove build artifacts"
	@echo "  run-mcp         - Start MCP server"

install:
	pip install -e ".[dev,agent]"

test:
	pytest tests/ -v --cov=src --cov-fail-under=85

test-unit:
	pytest tests/unit/ -v

test-integration:
	pytest tests/integration/ -v -m integration

test-hardware:
	pytest tests/hardware/ -v -m hardware --tb=short

test-coverage:
	pytest tests/ --cov=src --cov-fail-under=85 --cov-report=term-missing --cov-report=html
	@echo "Coverage report: htmlcov/index.html"

lint:
	ruff check src/ tests/

typecheck-touched:
	mypy --config-file mypy.ini src/utils/config.py src/mcp_server/server.py src/mcp_server/tools/anomaly_tools.py src/mcp_server/tools/sensor_tools.py src/mcp_server/ack_store.py src/mcp_server/session_store.py src/agents/langgraph_agent.py src/agents/llm_client.py src/models/base.py src/models/anomaly_detector.py src/models/fusion_engine.py src/models/hailo_adapter.py src/sensors/base.py src/sensors/bme680.py src/sensors/manager.py

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage htmlcov/ build/ dist/ *.egg-info

run-mcp:
	python -m mcp_server.server
