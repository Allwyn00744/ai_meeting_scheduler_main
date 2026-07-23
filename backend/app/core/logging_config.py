"""
Structured logging setup, applied once at process startup (see
app/main.py). Every `logging.getLogger(__name__)` call already
scattered throughout the codebase is unaffected in how it's called -
this only changes how the root logger formats and emits records, via
the standard library's own configuration surface (no new logging
calls anywhere else needed).

LOG_FORMAT=json emits one JSON object per line (safe for a log
aggregator to parse - CloudWatch/Datadog/ELK/etc. can all ingest this
directly) and includes the current request's ID (see
app/core/request_id.py) when a record is emitted from inside a
request. LOG_FORMAT=text (the default) keeps the traditional
human-readable single-line format for local development.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from app.core.config import settings
from app.core.request_id import get_request_id


class JsonFormatter(logging.Formatter):

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc,
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        request_id = get_request_id()
        if request_id:
            payload["request_id"] = request_id

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


class TextFormatter(logging.Formatter):
    """Same field order/content as JsonFormatter, one readable line - not a different feature set, just a different rendering."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        request_id = get_request_id()
        return f"{base} [request_id={request_id}]" if request_id else base


def configure_logging() -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.LOG_LEVEL.upper())

    # Replace any handlers a prior configure_logging() call (or a
    # library's own logging.basicConfig side effect) may have already
    # attached, so this is idempotent and always wins.
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)

    if settings.LOG_FORMAT.lower() == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            TextFormatter(
                fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S%z",
            )
        )

    root_logger.addHandler(handler)

    # uvicorn's own loggers otherwise bypass this formatting entirely
    # (they propagate to root by default in recent versions, but
    # pinning it here is explicit and version-independent).
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(logger_name).handlers = []
        logging.getLogger(logger_name).propagate = True
