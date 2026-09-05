"""Safe, opt-in standard logging helpers."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

_ALLOWED_FIELDS = frozenset(
    {
        "request_id",
        "stage",
        "duration_seconds",
        "retries",
        "provider",
        "status",
        "bytes",
        "cleanup",
        "usage",
        "model",
        "processing_mode",
        "media_resolution",
        "thinking_level",
        "fps",
        "attempt",
        "http_status",
        "error_type",
        "output_count",
        "total_bytes",
        "downloaded_bytes",
        "total_is_estimate",
        "phase",
        "percent",
    }
)
_request_id: ContextVar[str | None] = ContextVar(
    "video_context_pipeline_request_id", default=None
)


@contextmanager
def request_correlation(request_id: str | None = None):
    """Provide one request identifier to nested async log events."""
    value = request_id or uuid4().hex
    token: Token[str | None] = _request_id.set(value)
    try:
        yield value
    finally:
        _request_id.reset(token)


def current_request_id() -> str | None:
    """Return the correlation identifier active in this task context."""
    return _request_id.get()


def safe_log_fields(**fields: Any) -> dict[str, Any]:
    """Validate factual observability fields before they reach a logger."""
    unknown = set(fields) - _ALLOWED_FIELDS
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ValueError(f"unsafe log fields are not allowed: {names}")
    if "request_id" in fields and (
        not isinstance(fields["request_id"], str) or not fields["request_id"]
    ):
        raise ValueError("request_id must be a non-empty string")
    if "usage" in fields and not isinstance(fields["usage"], Mapping):
        raise ValueError("usage must be provider-reported mapping data")
    return dict(fields)


class JsonFormatter(logging.Formatter):
    """Emit only the message, level and explicitly allowlisted factual fields."""

    def format(self, record: logging.LogRecord) -> str:
        fields = getattr(record, "vcp_fields", {})
        if not isinstance(fields, Mapping):
            fields = {}
        body: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        body.update(safe_log_fields(**dict(fields)))
        return json.dumps(body, default=str, sort_keys=True)


def configure_json_logging(
    logger: logging.Logger | None = None, *, level: int = logging.INFO
) -> logging.Logger:
    """Attach an opt-in JSON console handler; importing this module changes nothing."""
    configured = logger or logging.getLogger("video_context_pipeline")
    configured.setLevel(level)
    if any(
        isinstance(handler.formatter, JsonFormatter) for handler in configured.handlers
    ):
        return configured
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    configured.addHandler(handler)
    configured.propagate = False
    return configured
