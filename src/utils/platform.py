"""Platform detection utilities for cross-platform compatibility.

Provides helpers to detect the host OS and return platform-appropriate
defaults (e.g. UART device paths) so that no Pi-specific values are
hardcoded in driver or config code.
"""

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OS detection
# ---------------------------------------------------------------------------


def is_linux() -> bool:
    """Return True when running on any Linux distribution."""
    return sys.platform.startswith("linux")


def is_macos() -> bool:
    """Return True when running on macOS (Darwin)."""
    return sys.platform == "darwin"


def is_raspberry_pi() -> bool:
    """Return True when running on a Raspberry Pi (any model).

    Checks the device-tree model file which is present on all Pi boards.
    """
    try:
        model = Path("/proc/device-tree/model").read_text()
        return "raspberry pi" in model.lower()
    except (FileNotFoundError, PermissionError, OSError):
        return False


# ---------------------------------------------------------------------------
# Platform-aware device path defaults
# ---------------------------------------------------------------------------

# Canonical defaults per platform — importable by constants.py or drivers.
_UART_DEFAULTS = {
    "pi": "/dev/ttyAMA0",
    "linux": "/dev/ttyUSB0",
    "mac": "/dev/tty.usbserial-0001",
}


def default_uart_port() -> str:
    """Return a sensible default UART device path for the current platform.

    On Raspberry Pi → ``/dev/ttyAMA0`` (GPIO header UART)
    On other Linux  → ``/dev/ttyUSB0`` (USB-serial adapter)
    On macOS        → ``/dev/tty.usbserial-0001`` (typical FTDI / CH340)
    """
    if is_raspberry_pi():
        port = _UART_DEFAULTS["pi"]
    elif is_linux():
        port = _UART_DEFAULTS["linux"]
    elif is_macos():
        port = _UART_DEFAULTS["mac"]
    else:
        port = _UART_DEFAULTS["linux"]
    logger.debug("Platform UART default: %s (sys.platform=%s)", port, sys.platform)
    return port
