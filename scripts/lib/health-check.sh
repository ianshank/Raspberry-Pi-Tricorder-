#!/usr/bin/env bash
set -euo pipefail

# Wait for a health endpoint to return HTTP success.
# Usage:
#   health-check.sh <url> [max_retries] [retry_delay_s] [connect_timeout_s] [label]
# Defaults can also be provided by environment variables:
#   HEALTH_CHECK_MAX_RETRIES, HEALTH_CHECK_RETRY_DELAY_S, HEALTH_CHECK_CONNECT_TIMEOUT_S

wait_for_health() {
    local url="${1:-}"
    local max_retries="${2:-${HEALTH_CHECK_MAX_RETRIES:-30}}"
    local retry_delay_s="${3:-${HEALTH_CHECK_RETRY_DELAY_S:-1}}"
    local connect_timeout_s="${4:-${HEALTH_CHECK_CONNECT_TIMEOUT_S:-5}}"
    local label="${5:-service}"

    if [[ -z "${url}" ]]; then
        echo "Error: health-check URL is required" >&2
        return 2
    fi

    local attempt
    for ((attempt = 1; attempt <= max_retries; attempt++)); do
        if curl -sf --connect-timeout "${connect_timeout_s}" "${url}" >/dev/null 2>&1; then
            echo "${label} is healthy (${url})"
            return 0
        fi
        echo "Waiting for ${label}: attempt ${attempt}/${max_retries} (sleep ${retry_delay_s}s)"
        sleep "${retry_delay_s}"
    done

    echo "${label} failed health check after ${max_retries} attempts (${url})" >&2
    return 1
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    wait_for_health "$@"
fi
