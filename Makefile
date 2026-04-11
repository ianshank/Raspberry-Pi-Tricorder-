.PHONY: help install test test-unit test-integration test-hardware test-coverage lint typecheck-touched clean run-mcp docker-build docker-up docker-down smoke-test deploy docker-build-arm64 docker-push docker-save bundle

PROJECT_PYTHONPATH ?= src
COVERAGE_FAIL_UNDER ?= 85
TRICORDER_PORT ?= 8000
SMOKE_URL ?= http://localhost:$(TRICORDER_PORT)
SMOKE_WS_URL ?= ws://localhost:$(TRICORDER_PORT)
HEALTH_CHECK_MAX_RETRIES ?= 30
HEALTH_CHECK_RETRY_DELAY_S ?= 1
HEALTH_CHECK_CONNECT_TIMEOUT_S ?= 5

PYTEST_CMD = PYTHONPATH=$(PROJECT_PYTHONPATH) python -m pytest

help:
	@echo "Available targets:"
	@echo "  install         - Install dependencies"
	@echo "  test            - Run all tests"
	@echo "  test-unit       - Run unit tests only"
	@echo "  test-integration- Run integration tests"
	@echo "  test-hardware   - Run hardware tests (requires Pi)"
	@echo "  test-coverage   - Run tests with coverage report"
	@echo "  lint            - Run linters"
	@echo "  typecheck-touched - Run mypy on touched modules"
	@echo "  clean           - Remove build artifacts"
	@echo "  run-mcp         - Start MCP server"
	@echo "  docker-build    - Build Docker image"
	@echo "  docker-up       - Start Docker container"
	@echo "  docker-down     - Stop Docker container"
	@echo "  smoke-test      - Build, start, smoke-test, teardown"
	@echo "  deploy          - Deploy to Raspberry Pi via SSH"

install:
	pip install -e ".[dev,agent]"

test:
	$(PYTEST_CMD) tests/ -v --cov=src --cov-fail-under=$(COVERAGE_FAIL_UNDER)

test-unit:
	$(PYTEST_CMD) tests/unit/ -v

test-integration:
	$(PYTEST_CMD) tests/integration/ -v -m integration

test-hardware:
	$(PYTEST_CMD) tests/hardware/ -v -m hardware --tb=short

test-coverage:
	$(PYTEST_CMD) tests/ --cov=src --cov-fail-under=$(COVERAGE_FAIL_UNDER) --cov-report=term-missing --cov-report=html
	@echo "Coverage report: htmlcov/index.html"

lint:
	ruff check src/ tests/

typecheck-touched:
	find src -name '*.py' -not -path '*/__pycache__/*' | xargs mypy --config-file mypy.ini

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage htmlcov/ build/ dist/ *.egg-info

run-mcp:
	PYTHONPATH=$(PROJECT_PYTHONPATH) python -m mcp_server.server

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down -v

smoke-test: docker-build docker-up
	@set -e; \
	trap 'docker compose down -v' EXIT; \
	echo "Waiting for container to become healthy..."; \
	bash scripts/lib/health-check.sh "$(SMOKE_URL)/health" "$(HEALTH_CHECK_MAX_RETRIES)" "$(HEALTH_CHECK_RETRY_DELAY_S)" "$(HEALTH_CHECK_CONNECT_TIMEOUT_S)" "Tricorder container"; \
	$(PYTEST_CMD) tests/smoke/ -v -m smoke --smoke-url $(SMOKE_URL) --smoke-ws-url $(SMOKE_WS_URL)

deploy:
	@if [ -z "$(PI_HOST)" ]; then echo "Usage: make deploy PI_HOST=<ip>"; exit 1; fi
	bash scripts/pi-deploy.sh $(PI_HOST)

# --- Docker build / push / bundle -------------------------------------------
TRICORDER_IMAGE_NAME ?= tricorder-neural
TRICORDER_IMAGE_TAG ?= latest
TRICORDER_REGISTRY ?= ghcr.io
TRICORDER_REGISTRY_OWNER ?=
TRICORDER_PLATFORM ?= linux/arm64

FULL_IMAGE_REF = $(TRICORDER_IMAGE_NAME):$(TRICORDER_IMAGE_TAG)
REGISTRY_REF = $(TRICORDER_REGISTRY)/$(TRICORDER_REGISTRY_OWNER)/$(TRICORDER_IMAGE_NAME):$(TRICORDER_IMAGE_TAG)

docker-build-arm64:
	docker buildx build --platform $(TRICORDER_PLATFORM) --tag $(FULL_IMAGE_REF) --load .

docker-push:
	@if [ -z "$(TRICORDER_REGISTRY_OWNER)" ]; then echo "TRICORDER_REGISTRY_OWNER is required (example: make docker-push TRICORDER_REGISTRY_OWNER=your-github-username)"; exit 1; fi
	docker tag $(FULL_IMAGE_REF) $(REGISTRY_REF)
	docker push $(REGISTRY_REF)

docker-save:
	docker save -o $(TRICORDER_IMAGE_NAME)-$(TRICORDER_IMAGE_TAG).tar $(FULL_IMAGE_REF)

bundle:
	@if [ "$(shell uname -s)" = "Darwin" ] || [ "$(shell uname -s)" = "Linux" ]; then \
		if [ -z "$(BUNDLE_TARGET)" ]; then echo "Usage: make bundle BUNDLE_TARGET=/path/to/drive"; exit 1; fi; \
		bash scripts/bundle-to-drive.sh "$(BUNDLE_TARGET)"; \
	else \
		echo "Use PowerShell:  .\\scripts\\bundle-to-drive.ps1 -TargetDrive F"; \
	fi
