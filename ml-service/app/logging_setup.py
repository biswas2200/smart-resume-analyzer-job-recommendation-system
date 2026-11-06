"""Logging for the ML service: one format for every module, tagged with the
request id the backend sends (X-Request-Id, see the backend's
RequestIdFilter) so one upload can be followed through both services' logs.

Log what happened and how long it took -- ids, domains, scores, counts,
timings. Never resume text, names, emails, phone numbers or file names:
uploaded resumes are personal data.
"""

import logging
import logging.config
import re
import uuid
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

# A caller-supplied id is echoed into logs, so only short, plain ids are kept.
_SAFE_ID_RE = re.compile(r"[A-Za-z0-9._-]{1,64}")

LOG_FORMAT = "%(asctime)s %(levelname)-5s [%(request_id)s] %(name)s: %(message)s"


def request_id_from(header: str | None) -> str:
    """The incoming id if it looks safe, otherwise a fresh one."""
    if header and _SAFE_ID_RE.fullmatch(header):
        return header
    return str(uuid.uuid4())


class RequestIdFilter(logging.Filter):
    """Stamps each record with the current request's id ("-" outside a request)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def configure_logging(level: str = "INFO", log_file: str = "") -> None:
    """Console logging for the app's own loggers (and, with log_file, a
    rotating file too). Uvicorn keeps its own handlers; the request middleware
    in main.py writes the access line with the request id."""
    handlers: dict = {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "filters": ["request_id"],
        }
    }
    if log_file:
        handlers["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": log_file,
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "encoding": "utf-8",
            "formatter": "standard",
            "filters": ["request_id"],
        }
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {"request_id": {"()": RequestIdFilter}},
            "formatters": {"standard": {"format": LOG_FORMAT}},
            "handlers": handlers,
            # Libraries (transformers, httpx, ...) only at WARNING; the app's
            # own loggers at the configured level.
            "root": {"level": "WARNING", "handlers": list(handlers)},
            "loggers": {"app": {"level": level.upper()}},
        }
    )
