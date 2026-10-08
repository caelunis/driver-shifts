"""Logging: one JSON object per line in containers, readable lines in a terminal.

Every record carries the request it belongs to (request_id) and who made it (user_id),
taken from context variables when the record is created, so the fields are there for
every handler, whatever thread formats the record later.

Events are logged with a short name as the message and details as `extra`:
    log.info("shift_started", extra={"driver_id": 7, "shift_id": 12})
Never log passwords, session tokens, cookies or request bodies.
"""

import logging
import sys
import traceback
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

import orjson
from pydantic_settings import BaseSettings, SettingsConfigDict

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_var: ContextVar[UUID | None] = ContextVar("user_id", default=None)

# Attributes every LogRecord has; anything else on a record came in through `extra`
_STANDARD = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime", "request_id", "user_id"}


class LogSettings(BaseSettings):
    """Separate from Settings: logging is set up before (and without) the database settings."""

    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "console"


def _extras(record: logging.LogRecord) -> dict[str, Any]:
    return {k: v for k, v in record.__dict__.items() if k not in _STANDARD and not k.startswith("_")}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("request_id", "user_id"):
            if (value := getattr(record, key, None)) is not None:
                entry[key] = value
        entry.update(_extras(record))
        if record.exc_info:
            entry["exc"] = "".join(traceback.format_exception(*record.exc_info))
        return orjson.dumps(entry, default=str).decode()


class ConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        time = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        rid = getattr(record, "request_id", None)
        prefix = f"{time} {record.levelname:<7} {record.name}" + (f" [{rid[:8]}]" if rid else "")
        details = " ".join(f"{k}={v}" for k, v in _extras(record).items())
        line = f"{prefix} {record.getMessage()}" + (f"  {details}" if details else "")
        if record.exc_info:
            line += "\n" + "".join(traceback.format_exception(*record.exc_info))
        return line


_base_factory = logging.getLogRecordFactory()


def _record_with_context(*args: Any, **kwargs: Any) -> logging.LogRecord:
    record = _base_factory(*args, **kwargs)
    record.request_id = request_id_var.get()
    record.user_id = user_id_var.get()
    return record


def configure_logging(settings: LogSettings | None = None) -> None:
    """Set up the root logger once per process; calling it again just reapplies settings."""
    settings = settings or LogSettings()
    logging.setLogRecordFactory(_record_with_context)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if settings.log_format == "json" else ConsoleFormatter())
    root = logging.getLogger()
    root.handlers = [h for h in root.handlers if not getattr(h, "_app_handler", False)]
    handler._app_handler = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())


def mask_email(email: str) -> str:
    """'driver@example.com' -> 'd***@example.com': enough to tell accounts apart in a log."""
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}" if domain else "***"
