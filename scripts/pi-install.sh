#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# pi-install.sh - Bootstrap installation for Raspberry Pi Tricorder
# =============================================================================
# Installs system dependencies, creates virtualenv, sets up systemd service,
# and enables hardware interfaces. Idempotent -- safe to run multiple times.
# =============================================================================

# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; }
section() { echo -e "\n${CYAN}=== $* ===${NC}"; }

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------
usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Bootstrap the Tricorder Neural Platform on a Raspberry Pi.

Environment variables:
  TRICORDER_INSTALL_DIR   Installation directory (default: /opt/tricorder)
    TRICORDER_ENVIRONMENT   Runtime environment (default: production)
    TRICORDER_BIND_HOST     MCP bind host (default: 0.0.0.0)
    TRICORDER_PORT          MCP bind port (default: 8000)
    TRICORDER_SERVICE_NAME  Systemd service name (default: tricorder-mcp)
    TRICORDER_SERVICE_USER  Systemd service user (default: tricorder)

Options:
  -h, --help    Show this help message and exit

This script is idempotent and safe to run multiple times.
EOF
    exit 0
}

[[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && usage

# ---------------------------------------------------------------------------
# Resolve script directory and load shared defaults
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=scripts/deploy.defaults.sh
source "${SCRIPT_DIR}/deploy.defaults.sh"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
INSTALL_DIR="${TRICORDER_INSTALL_DIR:-${PI_INSTALL_DIR}}"
SERVICE_NAME="${TRICORDER_SERVICE_NAME}"
SERVICE_USER="${TRICORDER_SERVICE_USER}"
TRICORDER_ENVIRONMENT="${TRICORDER_ENVIRONMENT}"
TRICORDER_BIND_HOST="${TRICORDER_BIND_HOST}"
TRICORDER_PORT="${TRICORDER_PORT}"
VENV_DIR="${INSTALL_DIR}/venv"

section "Tricorder Neural Platform - Pi Installer"
info "Install directory: ${INSTALL_DIR}"

# ---------------------------------------------------------------------------
# Architecture check
# ---------------------------------------------------------------------------
section "Checking architecture"
ARCH="$(uname -m)"
if [[ "${ARCH}" != "aarch64" ]]; then
    warn "Detected architecture '${ARCH}' -- expected aarch64 (Raspberry Pi 64-bit)."
    warn "Installation will continue, but hardware features may not work correctly."
else
    success "Architecture: ${ARCH}"
fi

# ---------------------------------------------------------------------------
# System dependencies
# ---------------------------------------------------------------------------
section "Installing system dependencies"
PACKAGES=(
    python3
    python3-venv
    python3-dev
    i2c-tools
    libgpiod-dev
    build-essential
    curl
)

info "Updating package lists..."
sudo apt-get update -qq

info "Installing packages: ${PACKAGES[*]}"
sudo apt-get install -y -qq "${PACKAGES[@]}"
success "System dependencies installed"

# ---------------------------------------------------------------------------
# Application directory
# ---------------------------------------------------------------------------
section "Setting up application directory"

if [[ ! -d "${INSTALL_DIR}" ]]; then
    info "Creating ${INSTALL_DIR}"
    sudo mkdir -p "${INSTALL_DIR}"
else
    info "Directory ${INSTALL_DIR} already exists"
fi

# Copy project files if running from source tree
PROJECT_DIR="$(dirname "${SCRIPT_DIR}")"
if [[ -f "${PROJECT_DIR}/setup.py" && "${PROJECT_DIR}" != "${INSTALL_DIR}" ]]; then
    info "Copying project files to ${INSTALL_DIR}..."
    sudo rsync -a --delete \
        --exclude-from "${SCRIPT_DIR}/rsync-excludes.txt" \
        "${PROJECT_DIR}/" "${INSTALL_DIR}/"
    success "Project files synced"
fi

# ---------------------------------------------------------------------------
# Virtual environment
# ---------------------------------------------------------------------------
section "Setting up Python virtual environment"

if [[ ! -d "${VENV_DIR}" ]]; then
    info "Creating virtualenv at ${VENV_DIR}"
    sudo python3 -m venv "${VENV_DIR}"
else
    info "Virtualenv already exists at ${VENV_DIR}"
fi

info "Upgrading pip..."
sudo "${VENV_DIR}/bin/pip" install --upgrade pip -q

info "Installing project with [hardware] extras..."
sudo "${VENV_DIR}/bin/pip" install -e "${INSTALL_DIR}[hardware]" -q
success "Python dependencies installed"

# ---------------------------------------------------------------------------
# System user
# ---------------------------------------------------------------------------
section "Setting up system user"

if id "${SERVICE_USER}" &>/dev/null; then
    info "User '${SERVICE_USER}' already exists"
else
    info "Creating system user '${SERVICE_USER}'..."
    sudo useradd \
        --system \
        --no-create-home \
        --shell /usr/sbin/nologin \
        --groups i2c,spi,dialout,gpio \
        "${SERVICE_USER}"
    success "User '${SERVICE_USER}' created"
fi

# Ensure group membership even if user already existed
for group in i2c spi dialout gpio; do
    if getent group "${group}" &>/dev/null; then
        sudo usermod -aG "${group}" "${SERVICE_USER}" 2>/dev/null || true
    fi
done
success "User groups configured"

# ---------------------------------------------------------------------------
# Data and log directories
# ---------------------------------------------------------------------------
section "Creating data and log directories"

sudo mkdir -p "${INSTALL_DIR}/data"
sudo mkdir -p "${INSTALL_DIR}/logs"
success "Directories created"

# ---------------------------------------------------------------------------
# Systemd service
# ---------------------------------------------------------------------------
section "Installing systemd service"

SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

info "Writing ${SERVICE_FILE}"
sudo tee "${SERVICE_FILE}" > /dev/null <<UNIT
[Unit]
Description=Tricorder Neural Platform MCP Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
Environment=PYTHONPATH=${INSTALL_DIR}/src
Environment=TRICORDER__ENVIRONMENT=${TRICORDER_ENVIRONMENT}
Environment=TRICORDER__MCP_SERVER__HOST=${TRICORDER_BIND_HOST}
Environment=TRICORDER__MCP_SERVER__PORT=${TRICORDER_PORT}
ExecStart=${VENV_DIR}/bin/python -m mcp_server.server
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNIT
success "Service file written"

sudo systemctl daemon-reload
success "Systemd daemon reloaded"

# ---------------------------------------------------------------------------
# Enable hardware interfaces
# ---------------------------------------------------------------------------
section "Configuring hardware interfaces"

if command -v raspi-config &>/dev/null; then
    info "Enabling I2C..."
    sudo raspi-config nonint do_i2c 0 2>/dev/null || warn "Could not enable I2C"

    info "Enabling SPI..."
    sudo raspi-config nonint do_spi 0 2>/dev/null || warn "Could not enable SPI"

    info "Enabling UART..."
    sudo raspi-config nonint do_serial_hw 0 2>/dev/null || warn "Could not enable UART"
    sudo raspi-config nonint do_serial 1 2>/dev/null || true

    success "Hardware interfaces configured"
else
    warn "raspi-config not found -- skipping hardware interface configuration"
    warn "Ensure I2C, SPI, and UART are enabled manually"
fi

# ---------------------------------------------------------------------------
# Set ownership and enable service
# ---------------------------------------------------------------------------
section "Finalizing installation"

info "Setting ownership of ${INSTALL_DIR} to ${SERVICE_USER}..."
sudo chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"
success "Ownership set"

info "Enabling ${SERVICE_NAME} service..."
sudo systemctl enable "${SERVICE_NAME}"
success "Service enabled"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
section "Installation Complete"
echo ""
success "Tricorder Neural Platform has been installed successfully!"
echo ""
info "  Install directory:  ${INSTALL_DIR}"
info "  Virtual environment: ${VENV_DIR}"
info "  Service name:        ${SERVICE_NAME}"
info "  Service user:        ${SERVICE_USER}"
echo ""
info "Useful commands:"
info "  sudo systemctl start ${SERVICE_NAME}     # Start the service"
info "  sudo systemctl status ${SERVICE_NAME}    # Check service status"
info "  sudo journalctl -u ${SERVICE_NAME} -f    # Follow logs"
echo ""
info "The service will listen on http://${TRICORDER_BIND_HOST}:${TRICORDER_PORT}"
info "Health endpoint: http://<pi-ip>:${TRICORDER_PORT}/health"
echo ""
