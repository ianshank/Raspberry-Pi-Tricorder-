#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# pi-load-image.sh - Load Docker image from offline bundle on Raspberry Pi
# =============================================================================

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; }
section() { echo -e "\n${CYAN}=== $* ===${NC}"; }

usage() {
    cat <<EOF
Usage: $(basename "$0") [BUNDLE_DIR]

Load a Tricorder Docker image from an offline bundle and start the service.

Arguments:
  BUNDLE_DIR    Path to the bundle directory (default: current directory)

Environment variables:
  TRICORDER_INSTALL_DIR  Where to install compose files (default: /opt/tricorder)
  TRICORDER_PORT         Service port (default: 8000)
EOF
    exit 0
}

[[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && usage

BUNDLE_DIR="${1:-.}"
INSTALL_DIR="${TRICORDER_INSTALL_DIR:-/opt/tricorder}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source shared defaults
if [[ -f "${BUNDLE_DIR}/scripts/deploy.defaults.sh" ]]; then
    source "${BUNDLE_DIR}/scripts/deploy.defaults.sh"
elif [[ -f "${SCRIPT_DIR}/deploy.defaults.sh" ]]; then
    source "${SCRIPT_DIR}/deploy.defaults.sh"
else
    error "Unable to load deploy defaults. Expected one of:"
    error "  - ${BUNDLE_DIR}/scripts/deploy.defaults.sh"
    error "  - ${SCRIPT_DIR}/deploy.defaults.sh"
    exit 1
fi

# Source health-check helper
if [[ -f "${BUNDLE_DIR}/scripts/lib/health-check.sh" ]]; then
    source "${BUNDLE_DIR}/scripts/lib/health-check.sh"
elif [[ -f "${SCRIPT_DIR}/lib/health-check.sh" ]]; then
    source "${SCRIPT_DIR}/lib/health-check.sh"
fi

section "Tricorder Offline Image Loader"
info "Bundle dir:  ${BUNDLE_DIR}"
info "Install dir: ${INSTALL_DIR}"

# Verify bundle
section "Verifying bundle"
if [[ ! -d "${BUNDLE_DIR}" ]]; then
    error "Bundle directory not found: ${BUNDLE_DIR}"
    exit 1
fi

TAR_FILE="$(find "${BUNDLE_DIR}" -maxdepth 1 -name '*.tar' | head -1)"
if [[ -z "${TAR_FILE}" ]]; then
    error "No .tar image file found in ${BUNDLE_DIR}"
    exit 1
fi
info "Image tar: ${TAR_FILE}"

if [[ -f "${BUNDLE_DIR}/SHA256SUMS.txt" ]]; then
    info "Verifying checksums..."
    cd "${BUNDLE_DIR}"
    if command -v sha256sum &>/dev/null; then
        if sha256sum --check --quiet SHA256SUMS.txt 2>/dev/null; then
            success "All checksums verified"
        else
            warn "Some checksums failed -- proceeding with caution"
        fi
    else
        warn "sha256sum not available -- skipping verification"
    fi
    cd - >/dev/null
else
    warn "No SHA256SUMS.txt found -- skipping verification"
fi

# Ensure Docker is installed
section "Checking Docker"
if ! command -v docker &>/dev/null; then
    info "Docker not found. Installing..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "${USER}"
    success "Docker installed"
else
    success "Docker is installed: $(docker --version)"
fi

# Load image
section "Loading Docker image"
info "Loading ${TAR_FILE} (this may take a minute)..."
sudo docker load -i "${TAR_FILE}"
success "Image loaded"
info "Available images:"
sudo docker images --format "  {{.Repository}}:{{.Tag}}  ({{.Size}})" | head -5

# Set up deployment
section "Setting up deployment"
sudo mkdir -p "${INSTALL_DIR}" "${INSTALL_DIR}/config" "${INSTALL_DIR}/data" "${INSTALL_DIR}/logs"

if [[ -f "${BUNDLE_DIR}/docker-compose.yml" ]]; then
    sudo cp "${BUNDLE_DIR}/docker-compose.yml" "${INSTALL_DIR}/docker-compose.yml"
    success "docker-compose.yml copied"
fi

if [[ -d "${BUNDLE_DIR}/config" ]]; then
    sudo cp -r "${BUNDLE_DIR}/config/"* "${INSTALL_DIR}/config/" 2>/dev/null || true
    success "Config files copied"
fi

if [[ -f "${BUNDLE_DIR}/.env" ]]; then
    sudo cp "${BUNDLE_DIR}/.env" "${INSTALL_DIR}/.env"
    success ".env copied from bundle"
else
    cat <<ENV | sudo tee "${INSTALL_DIR}/.env" > /dev/null
TRICORDER_PORT=${TRICORDER_PORT}
TRICORDER__ENVIRONMENT=${TRICORDER_ENVIRONMENT}
TRICORDER__MCP_SERVER__HOST=${TRICORDER_BIND_HOST}
ENV
    success ".env generated"
fi

# Start service
section "Starting Tricorder service"
cd "${INSTALL_DIR}"
info "Stopping any existing containers..."
sudo docker compose down 2>/dev/null || true
info "Starting container..."
sudo docker compose up -d
success "Container started"

# Health check
section "Verifying deployment"
HEALTH_URL="http://localhost:${TRICORDER_PORT}/health"
info "Checking ${HEALTH_URL}..."

if type wait_for_health &>/dev/null; then
    if wait_for_health "${HEALTH_URL}" "${HEALTH_CHECK_MAX_RETRIES}" "${HEALTH_CHECK_RETRY_DELAY_S}" "${HEALTH_CHECK_CONNECT_TIMEOUT_S}" "Tricorder"; then
        HEALTHY=true
    else
        HEALTHY=false
    fi
else
    HEALTHY=false
    for i in $(seq 1 "${HEALTH_CHECK_MAX_RETRIES:-30}"); do
        if curl -sf --connect-timeout "${HEALTH_CHECK_CONNECT_TIMEOUT_S:-5}" "${HEALTH_URL}" >/dev/null 2>&1; then
            HEALTHY=true; break
        fi
        sleep "${HEALTH_CHECK_RETRY_DELAY_S:-1}"
    done
fi

if [[ "${HEALTHY}" == "true" ]]; then
    success "Health check passed!"
    HEALTH_RESPONSE="$(curl -sf "${HEALTH_URL}" 2>/dev/null || echo '{}')"
    info "Health response: ${HEALTH_RESPONSE}"
else
    warn "Health endpoint did not respond"
    warn "Check logs: sudo docker compose -f ${INSTALL_DIR}/docker-compose.yml logs"
fi

# Summary
section "Deployment Summary"
echo ""
success "Offline deployment complete!"
echo ""
info "  Install dir: ${INSTALL_DIR}"
info "  Image:       $(basename "${TAR_FILE}" .tar)"
info "  URL:         http://$(hostname -I | awk '{print $1}'):${TRICORDER_PORT}"
info "  Health:      ${HEALTH_URL}"
echo ""
info "Useful commands:"
info "  sudo docker compose -f ${INSTALL_DIR}/docker-compose.yml logs -f"
info "  sudo docker compose -f ${INSTALL_DIR}/docker-compose.yml restart"
info "  sudo docker compose -f ${INSTALL_DIR}/docker-compose.yml down"
echo ""
