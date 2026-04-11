"""Tests for utils.platform — cross-platform detection utilities."""

from unittest.mock import patch

from utils.platform import (
    _UART_DEFAULTS,
    default_uart_port,
    is_linux,
    is_macos,
    is_raspberry_pi,
)


class TestIsLinux:
    def test_returns_true_on_linux(self):
        with patch("utils.platform.sys") as mock_sys:
            mock_sys.platform = "linux"
            assert is_linux() is True

    def test_returns_true_on_linux2(self):
        with patch("utils.platform.sys") as mock_sys:
            mock_sys.platform = "linux2"
            assert is_linux() is True

    def test_returns_false_on_darwin(self):
        with patch("utils.platform.sys") as mock_sys:
            mock_sys.platform = "darwin"
            assert is_linux() is False

    def test_returns_false_on_win32(self):
        with patch("utils.platform.sys") as mock_sys:
            mock_sys.platform = "win32"
            assert is_linux() is False


class TestIsMacos:
    def test_returns_true_on_darwin(self):
        with patch("utils.platform.sys") as mock_sys:
            mock_sys.platform = "darwin"
            assert is_macos() is True

    def test_returns_false_on_linux(self):
        with patch("utils.platform.sys") as mock_sys:
            mock_sys.platform = "linux"
            assert is_macos() is False


class TestIsRaspberryPi:
    def test_returns_true_with_pi_model_file(self):
        with patch("utils.platform.Path") as mock_path:
            mock_path.return_value.read_text.return_value = "Raspberry Pi 5 Model B Rev 1.0"
            assert is_raspberry_pi() is True

    def test_returns_false_with_non_pi_model(self):
        with patch("utils.platform.Path") as mock_path:
            mock_path.return_value.read_text.return_value = "NVIDIA Jetson Nano"
            assert is_raspberry_pi() is False

    def test_returns_false_when_file_missing(self):
        with patch("utils.platform.Path") as mock_path:
            mock_path.return_value.read_text.side_effect = FileNotFoundError
            assert is_raspberry_pi() is False

    def test_returns_false_on_permission_error(self):
        with patch("utils.platform.Path") as mock_path:
            mock_path.return_value.read_text.side_effect = PermissionError
            assert is_raspberry_pi() is False

    def test_returns_false_on_os_error(self):
        with patch("utils.platform.Path") as mock_path:
            mock_path.return_value.read_text.side_effect = OSError
            assert is_raspberry_pi() is False


class TestDefaultUartPort:
    def test_returns_pi_port_on_raspberry_pi(self):
        with patch("utils.platform.is_raspberry_pi", return_value=True):
            assert default_uart_port() == _UART_DEFAULTS["pi"]

    def test_returns_linux_port_on_generic_linux(self):
        with patch("utils.platform.is_raspberry_pi", return_value=False), \
             patch("utils.platform.is_linux", return_value=True):
            assert default_uart_port() == _UART_DEFAULTS["linux"]

    def test_returns_mac_port_on_macos(self):
        with patch("utils.platform.is_raspberry_pi", return_value=False), \
             patch("utils.platform.is_linux", return_value=False), \
             patch("utils.platform.is_macos", return_value=True):
            assert default_uart_port() == _UART_DEFAULTS["mac"]

    def test_returns_linux_fallback_on_unknown_platform(self):
        with patch("utils.platform.is_raspberry_pi", return_value=False), \
             patch("utils.platform.is_linux", return_value=False), \
             patch("utils.platform.is_macos", return_value=False):
            assert default_uart_port() == _UART_DEFAULTS["linux"]


class TestUartDefaults:
    def test_all_defaults_are_strings(self):
        for key, value in _UART_DEFAULTS.items():
            assert isinstance(value, str), f"_UART_DEFAULTS[{key!r}] should be str"

    def test_expected_keys(self):
        assert set(_UART_DEFAULTS.keys()) == {"pi", "linux", "mac"}
