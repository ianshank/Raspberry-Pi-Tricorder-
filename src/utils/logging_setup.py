"""Centralized logging configuration for Tricorder Neural Platform.

Supports both human-readable console output (development) and
structured JSON output (production) via structlog, while keeping
stdlib logging compatibility so existing ``logging.getLogger(__name__)``
calls continue to work unchanged.
"""

import logging
import logging.handlers
import uuid
from contextvars import ContextVar
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict

import structlog

if TYPE_CHECKING:
    from utils.config import LoggingConfig

# Correlation ID stored per-async-context for request tracing.
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


def set_correlation_id(cid: str | None = None) -> str:
    """Set (or generate) a correlation ID for the current context."""
    cid = cid or uuid.uuid4().hex[:16]
    correlation_id_var.set(cid)
    return cid


def _add_correlation_id(
    logger: Any, method_name: str, event_dict: Dict[str, Any]
) -> Dict[str, Any]:
    """Structlog processor that injects the current correlation ID."""
    cid = correlation_id_var.get("")
    if cid:
        event_dict["correlation_id"] = cid
    return event_dict


def setup_logging(config: "LoggingConfig") -> None:
    """
    Configure root logger with console and optional rotating file handler.

    When ``config.json_format`` is True the console renderer emits JSON lines
    suitable for log aggregators.  Otherwise a coloured, human-readable format
    is used.  Both modes integrate with stdlib so that third-party libraries
    using ``logging.getLogger()`` produce identical output.

    Args:
        config: LoggingConfig instance with level, format, file path settings
    """
    log_level = getattr(logging, config.level, logging.INFO)

    # --- stdlib root logger setup (file handler, base level) ---
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()

    formatter = logging.Formatter(config.format)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (optional)
    if config.file_path:
        file_path = Path(config.file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            filename=str(file_path),
            maxBytes=config.max_bytes,
            backupCount=config.backup_count,
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # --- structlog configuration ---
    json_format = config.json_format

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        _add_correlation_id,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if json_format:
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Replace the console handler formatter with structlog's ProcessorFormatter
    # so that *all* stdlib log records also pass through structlog processors.
    structlog_formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )
    console_handler.setFormatter(structlog_formatter)

    # Apply structlog formatter to file handler when JSON format is enabled
    if json_format and config.file_path:
        for handler in root_logger.handlers:
            if isinstance(handler, logging.handlers.RotatingFileHandler):
                handler.setFormatter(structlog_formatter)

    logging.getLogger(__name__).debug("Logging configured: level=%s json=%s", config.level, json_format)
