#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# firstboot-setup.sh — Generate Pi boot partition files for first-boot config
# =============================================================================
# Run this on your PC BEFORE ejecting the SD card. It writes files to the
# boot partition so the Pi auto-configures on first power-on.
#
# Usage: bash firstboot-setup.sh F:   (Windows drive letter of boot partition)
#   or:  bash firstboot-setup.sh /mnt/boot
# =============================================================================

BOOT_DIR="${1:?Boot directory argument is required. e.g. F: or /mnt/boot}"

if [[ ! -d "${BOOT_DIR}" ]]; then
    echo "Boot directory does not exist: ${BOOT_DIR}" >&2
    exit 1
fi

# Enable SSH
touch "${BOOT_DIR}/ssh"
echo "SSH enabled on ${BOOT_DIR}/ssh"

# Set hostname
HOSTNAME="${PI_HOSTNAME:-tricorder}"
echo "${HOSTNAME}" > "${BOOT_DIR}/hostname.txt"
echo "Hostname set to: ${HOSTNAME}"

# WiFi (optional)
WIFI_SSID="${PI_WIFI_SSID:-}"
WIFI_PASSWORD="${PI_WIFI_PASSWORD:-}"
WIFI_COUNTRY="${PI_WIFI_COUNTRY:-US}"

if [[ -n "${WIFI_SSID}" && -n "${WIFI_PASSWORD}" ]]; then
    cat > "${BOOT_DIR}/wpa_supplicant.conf" <<WPA
country=${WIFI_COUNTRY}
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1

network={
    ssid="${WIFI_SSID}"
    psk="${WIFI_PASSWORD}"
    key_mgmt=WPA-PSK
}
WPA
    echo "WiFi configured for: ${WIFI_SSID}"
else
    echo "WiFi not configured (set PI_WIFI_SSID and PI_WIFI_PASSWORD env vars)"
fi

echo ""
echo "First-boot files written to ${BOOT_DIR}"
echo "Eject the SD card and insert into Pi to boot."
