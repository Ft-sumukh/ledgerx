"""
LEDGER-ORBIT: Structured Logging Package
=========================================
Provides structured JSON logging with automatic context propagation via
Python contextvars. Every log record automatically includes correlation_id
and request_id, enabling cross-service log correlation.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Context variables (propagated automatically through async context)
# ---------------------------------------------------------------------------

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def bind_correlation_id(cid: str) -> None:
    """Set the correlation ID for the current async context."""
    correlation_id_var.set(cid)


def bind_request_id(rid: str) -> None:
    """Set the request ID for the current async context."""
    request_id_var.set(rid)


# ---------------------------------------------------------------------------
# JSON Log Formatter
# ---------------------------------------------------------------------------


class JsonFormatter(logging.Formatter):
    """Formats log records as newline-delimited JSON for log aggregation systems."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": correlation_id_var.get(""),
            "request_id": request_id_var.get(""),
            "module": record.module,
            "funcName": record.funcName,
            "lineno": record.lineno,
        }
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Include extra fields attached to the record
        _skip = {
            "name", "msg", "args", "levelname", "levelno", "pathname",
            "filename", "module", "exc_info", "exc_text", "stack_info",
            "lineno", "funcName", "created", "msecs", "relativeCreated",
            "thread", "threadName", "processName", "process", "message",
            "taskName",
        }
        for key, value in record.__dict__.items():
            if key not in _skip:
                log_data[key] = value

        return json.dumps(log_data, default=str)


class TextFormatter(logging.Formatter):
    """Human-readable formatter for local development."""

    _FMT = "%(asctime)s [%(levelname)-8s] %(name)s | %(message)s  (corr=%(correlation_id)s)"

    def format(self, record: logging.LogRecord) -> str:
        record.correlation_id = correlation_id_var.get("-")  # type: ignore[attr-defined]
        return super().format(record)


# ---------------------------------------------------------------------------
# Logger Factory
# ---------------------------------------------------------------------------


class OrbitLogger:
    """LEDGER-ORBIT logger factory. Call configure() once at application startup."""

    _configured = False

    @classmethod
    def configure(cls, level: str = "INFO", fmt: str = "json") -> None:
        if cls._configured:
            return
        handler = logging.StreamHandler(sys.stdout)
        if fmt == "json":
            handler.setFormatter(JsonFormatter())
        else:
            handler.setFormatter(
                TextFormatter(fmt=TextFormatter._FMT, datefmt="%Y-%m-%dT%H:%M:%S")
            )
        root = logging.getLogger()
        root.handlers.clear()
        root.addHandler(handler)
        root.setLevel(getattr(logging, level.upper(), logging.INFO))
        cls._configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger."""
    return logging.getLogger(name)
