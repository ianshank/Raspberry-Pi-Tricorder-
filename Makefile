.PHONY: help install test test-unit test-integration test-coverage lint clean run-mcp

help:
	@echo "Available targets:"
	@echo "  install         - Install dependencies"
	@echo "  test            - Run all tests"
	@echo "  test-unit       - Run unit tests only"
	@echo "  test-integration- Run integration tests"
	@echo "  test-coverage   - Run tests with coverage report"
	@echo "  lint            - Run linters"
	@echo "  clean           - Remove build artifacts"
	@echo "  run-mcp         - Start MCP server"

install:
	pip install -e ".[dev,agent]"

test:
	pytest tests/ -v

test-unit:
	pytest tests/unit/ -v

test-integration:
	pytest tests/integration/ -v -m integration

test-coverage:
	pytest tests/ --cov=src --cov-report=term-missing --cov-report=html
	@echo "Coverage report: htmlcov/index.html"

lint:
	ruff check src/ tests/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage htmlcov/ build/ dist/ *.egg-info

run-mcp:
	python -m mcp_server.server
