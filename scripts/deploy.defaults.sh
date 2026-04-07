#!/usr/bin/env bash
# Shared defaults for deployment and runtime scripts.

# SSH/deployment defaults
: "${PI_USER:=pi}"
: "${PI_PORT:=22}"
: "${PI_INSTALL_DIR:=/opt/tricorder}"
: "${PI_SSH_CONNECT_TIMEOUT_S:=10}"

# Tricorder runtime defaults
: "${TRICORDER_PORT:=8000}"
: "${TRICORDER_BIND_HOST:=0.0.0.0}"
: "${TRICORDER_ENVIRONMENT:=production}"
: "${TRICORDER_SERVICE_NAME:=tricorder-mcp}"
: "${TRICORDER_SERVICE_USER:=tricorder}"

# Health-check defaults
: "${HEALTH_CHECK_MAX_RETRIES:=30}"
: "${HEALTH_CHECK_RETRY_DELAY_S:=1}"
: "${HEALTH_CHECK_CONNECT_TIMEOUT_S:=5}"

# Docker image defaults
: "${TRICORDER_IMAGE_NAME:=tricorder-neural}"
: "${TRICORDER_IMAGE_TAG:=latest}"
: "${TRICORDER_REGISTRY:=ghcr.io}"
: "${TRICORDER_REGISTRY_OWNER:=}"
: "${TRICORDER_PLATFORM:=linux/arm64}"

# Offline bundle defaults
: "${BUNDLE_DIR:=tricorder-deploy}"
