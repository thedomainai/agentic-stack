"""
Structured logging utilities for Agentic Stack.

Provides JSON-formatted logging with support for JSONL file output.
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


class JSONFormatter(logging.Formatter):
    """Custom formatter that outputs log records as JSON."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields
        if hasattr(record, "agent_id"):
            log_entry["agent_id"] = record.agent_id
        if hasattr(record, "task_id"):
            log_entry["task_id"] = record.task_id
        if hasattr(record, "correlation_id"):
            log_entry["correlation_id"] = record.correlation_id

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Add any extra attributes
        for key, value in record.__dict__.items():
            if key not in (
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "pathname", "process", "processName", "relativeCreated",
                "stack_info", "exc_info", "exc_text", "thread", "threadName",
                "agent_id", "task_id", "correlation_id", "message",
            ):
                if not key.startswith("_"):
                    log_entry[key] = value

        return json.dumps(log_entry)


class JSONLFileHandler(logging.Handler):
    """Handler that writes log records to a JSONL file."""

    def __init__(self, filepath: Path, mode: str = "a"):
        """Initialize the handler."""
        super().__init__()
        self.filepath = filepath
        self.mode = mode
        self.formatter = JSONFormatter()

        # Ensure directory exists
        self.filepath.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, record: logging.LogRecord) -> None:
        """Write log record to file."""
        try:
            msg = self.format(record)
            with open(self.filepath, self.mode, encoding="utf-8") as f:
                f.write(msg + "\n")
        except Exception:
            self.handleError(record)


def setup_logging(
    level: str = "INFO",
    format_type: str = "json",
    log_file: Path | None = None,
) -> None:
    """
    Set up logging configuration.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_type: Output format ('json' or 'text')
        log_file: Optional path to log file
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper()))

    if format_type == "json":
        console_handler.setFormatter(JSONFormatter())
    else:
        console_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
        )

    root_logger.addHandler(console_handler)

    # File handler (if specified)
    if log_file:
        file_handler = JSONLFileHandler(log_file)
        file_handler.setLevel(getattr(logging, level.upper()))
        root_logger.addHandler(file_handler)


def get_logger(
    name: str,
    agent_id: str | None = None,
    task_id: str | None = None,
) -> logging.Logger:
    """
    Get a logger instance with optional context.

    Args:
        name: Logger name (usually __name__)
        agent_id: Optional agent identifier for context
        task_id: Optional task identifier for context

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Create adapter with extra context if provided
    if agent_id or task_id:
        extra = {}
        if agent_id:
            extra["agent_id"] = agent_id
        if task_id:
            extra["task_id"] = task_id

        return logging.LoggerAdapter(logger, extra)

    return logger
