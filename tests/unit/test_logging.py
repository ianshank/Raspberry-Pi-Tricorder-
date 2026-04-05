"""Unit tests for logging setup."""

import pytest
import logging
from pathlib import Path

from utils.config import LoggingConfig
from utils.logging_setup import setup_logging


class TestLoggingSetup:
    def test_setup_console_only(self):
        config = LoggingConfig(level="DEBUG", file_path=None)
        setup_logging(config)
        root = logging.getLogger()
        assert root.level == logging.DEBUG
        # Should have at least console handler
        assert len(root.handlers) >= 1

    def test_setup_with_file(self, tmp_path):
        log_file = tmp_path / "test.log"
        config = LoggingConfig(
            level="INFO",
            file_path=str(log_file),
            max_bytes=1024,
            backup_count=2,
        )
        setup_logging(config)
        root = logging.getLogger()
        assert root.level == logging.INFO
        # Should have console + file handler
        assert len(root.handlers) >= 2

    def test_setup_creates_log_dir(self, tmp_path):
        log_file = tmp_path / "subdir" / "test.log"
        config = LoggingConfig(level="WARNING", file_path=str(log_file))
        setup_logging(config)
        assert log_file.parent.exists()

    def test_setup_clears_handlers(self):
        config = LoggingConfig(level="INFO", file_path=None)
        setup_logging(config)
        count1 = len(logging.getLogger().handlers)
        setup_logging(config)  # Re-init should not duplicate
        count2 = len(logging.getLogger().handlers)
        assert count2 == count1

    def test_log_levels(self):
        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            config = LoggingConfig(level=level, file_path=None)
            setup_logging(config)
            assert logging.getLogger().level == getattr(logging, level)
