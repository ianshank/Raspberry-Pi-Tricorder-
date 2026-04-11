#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# pi-configure.sh - Remote Raspberry Pi configuration for Tricorder
# =============================================================================
# Configures hostname, WiFi, locale, hardware interfaces, and optionally
# installs the Tricorder service if not already present.
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

Configure a Raspberry Pi for the Tricorder Neural Platform.

Arguments:
  PI_HOST               Hostname or IP of the Raspberry Pi (required)

Environment variables:
  PI_HOST               Alternative to positional argument
  PI_USER               SSH user (default: pi)
  PI_PORT               SSH port (default: 22)
  PI_SSH_KEY            Path to SSH private key (optional)
  PI_INSTALL_DIR        Installation directory on Pi (default: /opt/tricorder)
  PI_HOSTNAME           Set Pi hostname (optional)
  PI_WIFI_SSID          WiFi network name (optional)
  PI_WIFI_PASSWORD      WiFi password (required if PI_WIFI_SSID is set)
  PI_LOCALE             System locale (default: en_US.UTF-8)
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
  PI_HOSTNAME=tricorder PI_WIFI_SSID=MyNetwork PI_WIFI_PASSWORD=secret $(basename "$0") 192.168.1.100
  PI_LOCALE=en_GB.UTF-8 $(basename "$0") tricorder.local
EOF
    exit 0
}

[[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && usage

# ---------------------------------------------------------------------------
# Resolve script directory and load shared defaults/helpers
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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
PI_HOSTNAME="${PI_HOSTNAME:-}"
PI_WIFI_SSID="${PI_WIFI_SSID:-}"
PI_WIFI_PASSWORD="${PI_WIFI_PASSWORD:-}"
PI_LOCALE="${PI_LOCALE:-en_US.UTF-8}"
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

# Helper to run commands on Pi
run_remote() {
    ssh "${SSH_OPTS[@]}" "${SSH_TARGET}" "$@"
}

section "Tricorder Neural Platform - Pi Configuration"
info "Target:      ${SSH_TARGET}:${PI_PORT}"
info "Install dir: ${PI_INSTALL_DIR}"

# ---------------------------------------------------------------------------
# Validate SSH connectivity
# ---------------------------------------------------------------------------
section "Validating SSH connectivity"

info "Testing connection to ${SSH_TARGET}..."
if run_remote "echo 'SSH connection successful'" 2>/dev/null; then
    success "SSH connection verified"
else
    error "Cannot connect to ${SSH_TARGET} on port ${PI_PORT}"
    error "Check that the Pi is reachable and SSH is enabled."
    exit 1
fi

# ---------------------------------------------------------------------------
# Hostname
# ---------------------------------------------------------------------------
if [[ -n "${PI_HOSTNAME}" ]]; then
    section "Setting hostname"
    info "Setting hostname to '${PI_HOSTNAME}'..."

    run_remote "sudo hostnamectl set-hostname '${PI_HOSTNAME}'" 2>/dev/null \
        || run_remote "sudo raspi-config nonint do_hostname '${PI_HOSTNAME}'" 2>/dev/null \
        || warn "Could not set hostname"

    CURRENT_HOSTNAME="$(run_remote 'hostname' 2>/dev/null || echo 'unknown')"
    if [[ "${CURRENT_HOSTNAME}" == "${PI_HOSTNAME}" ]]; then
        success "Hostname set to '${PI_HOSTNAME}'"
    else
        warn "Hostname may require a reboot to take effect"
    fi
else
    info "PI_HOSTNAME not set -- skipping hostname configuration"
fi

# ---------------------------------------------------------------------------
# WiFi
# ---------------------------------------------------------------------------
if [[ -n "${PI_WIFI_SSID}" ]]; then
    section "Configuring WiFi"

    if [[ -z "${PI_WIFI_PASSWORD}" ]]; then
        error "PI_WIFI_PASSWORD is required when PI_WIFI_SSID is set"
        exit 1
    fi

    info "Connecting to WiFi network '${PI_WIFI_SSID}'..."

    if run_remote "command -v nmcli" &>/dev/null; then
        run_remote "sudo nmcli device wifi connect '${PI_WIFI_SSID}' password '${PI_WIFI_PASSWORD}'" 2>/dev/null \
            && success "Connected to '${PI_WIFI_SSID}' via nmcli" \
            || warn "nmcli WiFi connection failed -- check credentials"
    else
        warn "nmcli not found. Attempting raspi-config..."
        run_remote "sudo raspi-config nonint do_wifi_ssid_passphrase '${PI_WIFI_SSID}' '${PI_WIFI_PASSWORD}'" 2>/dev/null \
            && success "WiFi configured via raspi-config (reboot may be required)" \
            || warn "Could not configure WiFi -- set up manually"
    fi
else
    info "PI_WIFI_SSID not set -- skipping WiFi configuration"
fi

# ---------------------------------------------------------------------------
# Locale
# ---------------------------------------------------------------------------
section "Configuring locale"

info "Setting locale to '${PI_LOCALE}'..."
run_remote "sudo locale-gen '${PI_LOCALE}' 2>/dev/null; sudo update-locale LANG='${PI_LOCALE}' 2>/dev/null" \
    && success "Locale set to '${PI_LOCALE}'" \
    || warn "Could not configure locale"

# ---------------------------------------------------------------------------
# Hardware interfaces
# ---------------------------------------------------------------------------
section "Enabling hardware interfaces"

if run_remote "command -v raspi-config" &>/dev/null; then
    info "Enabling I2C..."
    run_remote "sudo raspi-config nonint do_i2c 0" 2>/dev/null \
        && success "I2C enabled" \
        || warn "Could not enable I2C"

    info "Enabling SPI..."
    run_remote "sudo raspi-config nonint do_spi 0" 2>/dev/null \
        && success "SPI enabled" \
        || warn "Could not enable SPI"

    info "Enabling UART..."
    run_remote "sudo raspi-config nonint do_serial_hw 0" 2>/dev/null \
        && success "UART hardware enabled" \
        || warn "Could not enable UART hardware"
    run_remote "sudo raspi-config nonint do_serial 1" 2>/dev/null || true

    info "Enabling camera interface..."
    run_remote "sudo raspi-config nonint do_camera 0" 2>/dev/null \
        && success "Camera enabled" \
        || info "Camera interface not applicable or already enabled"
else
    warn "raspi-config not found on remote host"
    warn "Hardware interfaces must be configured manually"
fi

# ---------------------------------------------------------------------------
# Install Tricorder service if not present
# ---------------------------------------------------------------------------
section "Checking Tricorder service"

if run_remote "systemctl list-unit-files | grep -q -- '${SERVICE_NAME}'" 2>/dev/null; then
    success "${SERVICE_NAME} service already exists"
else
    warn "${SERVICE_NAME} service not found -- running installation"

    if run_remote "test -f '${PI_INSTALL_DIR}/scripts/pi-install.sh'" 2>/dev/null; then
        info "Running pi-install.sh from ${PI_INSTALL_DIR}..."
        run_remote "TRICORDER_INSTALL_DIR='${PI_INSTALL_DIR}' TRICORDER_PORT='${TRICORDER_PORT}' TRICORDER_BIND_HOST='${TRICORDER_BIND_HOST}' TRICORDER_ENVIRONMENT='${TRICORDER_ENVIRONMENT}' TRICORDER_SERVICE_NAME='${TRICORDER_SERVICE_NAME}' TRICORDER_SERVICE_USER='${TRICORDER_SERVICE_USER}' bash '${PI_INSTALL_DIR}/scripts/pi-install.sh'"
        success "Installation completed"
    else
        warn "pi-install.sh not found at ${PI_INSTALL_DIR}/scripts/"
        warn "Run pi-deploy.sh first to copy project files, then re-run this script."
    fi
fi

# ---------------------------------------------------------------------------
# Verify health endpoint
# ---------------------------------------------------------------------------
section "Verifying service health"

# Ensure service is running
if run_remote "systemctl is-active ${SERVICE_NAME}" &>/dev/null; then
    info "Service is active, checking health endpoint..."
else
    info "Starting ${SERVICE_NAME} service..."
    run_remote "sudo systemctl start ${SERVICE_NAME}" 2>/dev/null || true
    sleep 3
fi

HEALTH_URL="http://${PI_HOST}:${HEALTH_ENDPOINT_PORT}/health"

info "Checking ${HEALTH_URL}..."
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
    warn "Check service status: ssh ${SSH_TARGET} 'sudo systemctl status ${SERVICE_NAME}'"
fi

# ---------------------------------------------------------------------------
# Configuration summary
# ---------------------------------------------------------------------------
section "Configuration Summary"
echo ""
success "Raspberry Pi configuration complete!"
echo ""
info "  Host:          ${PI_HOST}"
info "  User:          ${PI_USER}"
info "  Port:          ${PI_PORT}"
info "  Install dir:   ${PI_INSTALL_DIR}"
[[ -n "${PI_HOSTNAME}" ]]   && info "  Hostname:      ${PI_HOSTNAME}"
[[ -n "${PI_WIFI_SSID}" ]]  && info "  WiFi SSID:     ${PI_WIFI_SSID}"
info "  Locale:        ${PI_LOCALE}"
echo ""
info "  Hardware interfaces:"
info "    I2C:   enabled"
info "    SPI:   enabled"
info "    UART:  enabled"
echo ""
if [[ "${HEALTHY}" == "true" ]]; then
    info "  Service status: RUNNING"
    info "  Application URL:  http://${PI_HOST}:${HEALTH_ENDPOINT_PORT}"
    info "  Health endpoint:  ${HEALTH_URL}"
else
    warn "  Service status: NOT VERIFIED"
    info "  Check: ssh ${SSH_TARGET} 'sudo systemctl status ${SERVICE_NAME}'"
fi
echo ""
