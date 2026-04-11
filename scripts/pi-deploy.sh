#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# pi-deploy.sh - SSH-based deployment to a Raspberry Pi
# =============================================================================
# Syncs project files via rsync, runs pi-install.sh on the target, restarts
# the service, and verifies the health endpoint.
# =============================================================================

# ---------------------------------------------------------------------------
# Color helpers (shared)
# ---------------------------------------------------------------------------
# shellcheck source=scripts/lib/colors.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/colors.sh"

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------
usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS] [PI_HOST]

Deploy the Tricorder Neural Platform to a Raspberry Pi over SSH.

Arguments:
  PI_HOST               Hostname or IP of the Raspberry Pi (required)

Environment variables:
  PI_HOST               Alternative to positional argument
  PI_USER               SSH user (default: pi)
  PI_PORT               SSH port (default: 22)
  PI_SSH_KEY            Path to SSH private key (optional)
  PI_INSTALL_DIR        Installation directory on Pi (default: /opt/tricorder)
    TRICORDER_PORT        Service port used for health checks (default: 8000)
    TRICORDER_BIND_HOST   Service bind host for install step (default: 0.0.0.0)
    TRICORDER_ENVIRONMENT Runtime environment for install step (default: production)
    TRICORDER_SERVICE_NAME Systemd service name (default: tricorder-mcp)
    TRICORDER_SERVICE_USER Systemd service user (default: tricorder)
    HEALTH_CHECK_MAX_RETRIES       Health check retry count (default: 30)
    HEALTH_CHECK_RETRY_DELAY_S     Delay between retries in seconds (default: 1)
    HEALTH_CHECK_CONNECT_TIMEOUT_S Curl connect timeout in seconds (default: 5)

Options:
  -h, --help            Show this help message and exit

Examples:
  $(basename "$0") 192.168.1.100
  PI_HOST=tricorder.local PI_USER=admin $(basename "$0")
  PI_SSH_KEY=~/.ssh/pi_key $(basename "$0") 192.168.1.100
EOF
    exit 0
}

[[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && usage

# ---------------------------------------------------------------------------
# Resolve script + project directories
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "${SCRIPT_DIR}")"

# shellcheck source=scripts/deploy.defaults.sh
source "${SCRIPT_DIR}/deploy.defaults.sh"
# shellcheck source=scripts/lib/health-check.sh
source "${SCRIPT_DIR}/lib/health-check.sh"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PI_HOST="${1:-${PI_HOST:-}}"
PI_USER="${PI_USER}"
PI_PORT="${PI_PORT}"
PI_SSH_KEY="${PI_SSH_KEY:-}"
PI_INSTALL_DIR="${PI_INSTALL_DIR}"
SERVICE_NAME="${TRICORDER_SERVICE_NAME}"
HEALTH_ENDPOINT_PORT="${TRICORDER_PORT}"

if [[ -z "${PI_HOST}" ]]; then
    error "PI_HOST is required. Provide as first argument or set the PI_HOST env var."
    echo ""
    usage
fi

# Build SSH options
SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout="${PI_SSH_CONNECT_TIMEOUT_S}" -p "${PI_PORT}")
if [[ -n "${PI_SSH_KEY}" ]]; then
    SSH_OPTS+=(-i "${PI_SSH_KEY}")
fi

SSH_TARGET="${PI_USER}@${PI_HOST}"

section "Tricorder Neural Platform - Deployment"
info "Target:      ${SSH_TARGET}:${PI_PORT}"
info "Install dir: ${PI_INSTALL_DIR}"
info "Source:      ${PROJECT_DIR}"

# ---------------------------------------------------------------------------
# Validate SSH connectivity
# ---------------------------------------------------------------------------
section "Validating SSH connectivity"

info "Testing connection to ${SSH_TARGET}..."
if ssh "${SSH_OPTS[@]}" "${SSH_TARGET}" "echo 'SSH connection successful'" 2>/dev/null; then
    success "SSH connection verified"
else
    error "Cannot connect to ${SSH_TARGET} on port ${PI_PORT}"
    error "Check that the Pi is reachable and SSH is enabled."
    exit 1
fi

# ---------------------------------------------------------------------------
# Sync project files via rsync
# ---------------------------------------------------------------------------
section "Syncing project files"

RSYNC_OPTS=(
    -az
    --delete
    --exclude-from "${SCRIPT_DIR}/rsync-excludes.txt"
)

# rsync SSH transport options
RSYNC_SSH="ssh ${SSH_OPTS[*]}"

info "Rsyncing project to ${SSH_TARGET}:${PI_INSTALL_DIR}/..."
ssh "${SSH_OPTS[@]}" "${SSH_TARGET}" "sudo mkdir -p '${PI_INSTALL_DIR}' && sudo chown '${PI_USER}:${PI_USER}' '${PI_INSTALL_DIR}'"

rsync "${RSYNC_OPTS[@]}" -e "${RSYNC_SSH}" \
    "${PROJECT_DIR}/" \
    "${SSH_TARGET}:${PI_INSTALL_DIR}/"

success "Project files synced"

# ---------------------------------------------------------------------------
# Run pi-install.sh on the Pi
# ---------------------------------------------------------------------------
section "Running installation on Pi"

info "Executing pi-install.sh remotely..."
ssh "${SSH_OPTS[@]}" "${SSH_TARGET}" \
    "TRICORDER_INSTALL_DIR='${PI_INSTALL_DIR}' TRICORDER_PORT='${TRICORDER_PORT}' TRICORDER_BIND_HOST='${TRICORDER_BIND_HOST}' TRICORDER_ENVIRONMENT='${TRICORDER_ENVIRONMENT}' TRICORDER_SERVICE_NAME='${TRICORDER_SERVICE_NAME}' TRICORDER_SERVICE_USER='${TRICORDER_SERVICE_USER}' bash '${PI_INSTALL_DIR}/scripts/pi-install.sh'"

success "Installation completed on Pi"

# ---------------------------------------------------------------------------
# Restart the service
# ---------------------------------------------------------------------------
section "Restarting service"

info "Restarting ${SERVICE_NAME} service..."
ssh "${SSH_OPTS[@]}" "${SSH_TARGET}" "sudo systemctl restart ${SERVICE_NAME}"
success "Service restarted"

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
section "Verifying deployment"

HEALTH_URL="http://${PI_HOST}:${HEALTH_ENDPOINT_PORT}/health"

info "Waiting for health endpoint at ${HEALTH_URL}..."

if wait_for_health \
    "${HEALTH_URL}" \
    "${HEALTH_CHECK_MAX_RETRIES}" \
    "${HEALTH_CHECK_RETRY_DELAY_S}" \
    "${HEALTH_CHECK_CONNECT_TIMEOUT_S}" \
    "${SERVICE_NAME}"; then
    HEALTHY=true
else
    HEALTHY=false
fi

if [[ "${HEALTHY}" == "true" ]]; then
    success "Health check passed!"
    HEALTH_RESPONSE="$(curl -sf "${HEALTH_URL}" 2>/dev/null || echo '{}')"
    info "Health response: ${HEALTH_RESPONSE}"
else
    warn "Health endpoint did not respond after ${HEALTH_CHECK_MAX_RETRIES} attempts"
    warn "The service may still be starting. Check with:"
    warn "  ssh ${SSH_TARGET} 'sudo systemctl status ${SERVICE_NAME}'"
    warn "  ssh ${SSH_TARGET} 'sudo journalctl -u ${SERVICE_NAME} -n 50'"
fi

# ---------------------------------------------------------------------------
# Deployment summary
# ---------------------------------------------------------------------------
section "Deployment Summary"
echo ""
success "Deployment to ${PI_HOST} complete!"
echo ""
info "  Host:          ${PI_HOST}"
info "  User:          ${PI_USER}"
info "  Port:          ${PI_PORT}"
info "  Install dir:   ${PI_INSTALL_DIR}"
info "  Service:       ${SERVICE_NAME}"
echo ""
info "  Application URL:  http://${PI_HOST}:${HEALTH_ENDPOINT_PORT}"
info "  Health endpoint:  ${HEALTH_URL}"
info "  WebSocket:        ws://${PI_HOST}:${HEALTH_ENDPOINT_PORT}/ws/sensors"
echo ""
info "Useful commands:"
info "  ssh ${SSH_TARGET} 'sudo systemctl status ${SERVICE_NAME}'"
info "  ssh ${SSH_TARGET} 'sudo journalctl -u ${SERVICE_NAME} -f'"
echo ""
