import datetime as dt
import logging
import logging.config
import logging.handlers
import sys
import threading
import uuid
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from config import settings

LOG_RECORD_BUILTIN_ATTRS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
    "taskName",
}

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")
user_id_ctx: ContextVar[str] = ContextVar("user_id", default="-")
operation_ctx: ContextVar[str] = ContextVar("operation", default="-")


class MyJSONFormatter(logging.Formatter):
    def __init__(self, *, fmt_keys: dict[str, str] | None = None):
        super().__init__()
        self.fmt_keys = fmt_keys if fmt_keys is not None else {}

    def format(self, record: logging.LogRecord) -> str:
        message = self._prepare_log_dict(record)
        import json

        return json.dumps(message, default=str)

    def _prepare_log_dict(self, record: logging.LogRecord) -> dict[str, Any]:
        always_fields: dict[str, Any] = {
            "message": record.getMessage(),
            "timestamp": dt.datetime.fromtimestamp(record.created, tz=dt.UTC).isoformat(),
        }
        if record.exc_info is not None:
            always_fields["exc_info"] = self.formatException(record.exc_info)

        if record.stack_info is not None:
            always_fields["stack_info"] = self.formatStack(record.stack_info)

        message = {
            key: msg_val
            if (msg_val := always_fields.pop(val, None)) is not None
            else getattr(record, val)
            for key, val in self.fmt_keys.items()
        }
        message.update(always_fields)

        for key, val in record.__dict__.items():
            if key not in LOG_RECORD_BUILTIN_ATTRS:
                message[key] = val

        return message


class NonErrorFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno <= logging.INFO


class ErrorOnlyFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= logging.WARNING


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        record.user_id = user_id_ctx.get()
        record.operation = operation_ctx.get()
        return True


def set_log_context(
    *, request_id: str | None = None, user_id: str | None = None, operation: str | None = None
) -> None:
    if request_id is not None:
        request_id_ctx.set(request_id)
    if user_id is not None:
        user_id_ctx.set(user_id)
    if operation is not None:
        operation_ctx.set(operation)


def clear_log_context() -> None:
    request_id_ctx.set("-")
    user_id_ctx.set("-")
    operation_ctx.set("-")


def _ensure_log_dir(log_file: str) -> None:
    log_path = Path(log_file)
    if log_path.parent and str(log_path.parent) not in {"", "."}:
        log_path.parent.mkdir(parents=True, exist_ok=True)


def _build_logging_config(log_level: str, json_logs: bool) -> dict[str, Any]:
    file_format = (
        "%(asctime)s [%(levelname)s] [%(name)s] "
        "[request_id=%(request_id)s user_id=%(user_id)s op=%(operation)s] %(message)s"
    )

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "non_error": {"()": "utilities.logging.NonErrorFilter"},
            "error_only": {"()": "utilities.logging.ErrorOnlyFilter"},
            "context": {"()": "utilities.logging.ContextFilter"},
        },
        "formatters": {
            "plain": {
                "format": file_format,
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "json": {
                "()": "utilities.logging.MyJSONFormatter",
                "fmt_keys": {
                    "level": "levelname",
                    "logger": "name",
                    "module": "module",
                    "line": "lineno",
                    "request_id": "request_id",
                    "user_id": "user_id",
                    "operation": "operation",
                },
            },
        },
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "level": log_level,
                "formatter": "json" if json_logs else "plain",
                "filters": ["non_error", "context"],
                "stream": "ext://sys.stdout",
            },
            "stderr": {
                "class": "logging.StreamHandler",
                "level": "WARNING",
                "formatter": "json" if json_logs else "plain",
                "filters": ["error_only", "context"],
                "stream": "ext://sys.stderr",
            },
            "rotating_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": log_level,
                "formatter": "json" if json_logs else "plain",
                "filters": ["context"],
                "filename": settings.LOG_FILE,
                "maxBytes": settings.LOG_MAX_BYTES,
                "backupCount": settings.LOG_BACKUP_COUNT,
                "encoding": "utf-8",
            },
        },
        "root": {
            "level": log_level,
            "handlers": ["stdout", "stderr", "rotating_file"],
        },
        "loggers": {
            "uvicorn": {"propagate": True},
            "uvicorn.error": {"propagate": True},
            "uvicorn.access": {"propagate": True},
        },
    }


def _install_global_exception_hooks() -> None:
    logger = logging.getLogger("utilities.global_exceptions")

    def handle_exception(exc_type, exc_value, exc_traceback) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        error_id = str(uuid.uuid4())
        logger.critical(
            "Unhandled exception",
            extra={"error_id": error_id},
            exc_info=(exc_type, exc_value, exc_traceback),
        )

    def handle_thread_exception(args: threading.ExceptHookArgs) -> None:
        if args.exc_type is None:
            return
        handle_exception(args.exc_type, args.exc_value, args.exc_traceback)

    sys.excepthook = handle_exception
    threading.excepthook = handle_thread_exception


def log_exception_with_id(
    logger: logging.Logger, message: str, exc: Exception, **context: Any
) -> str:
    error_id = str(uuid.uuid4())
    logger.exception(message, extra={"error_id": error_id, **context})
    return error_id


def initialize_logging(log_level: str | None = None, json_logs: bool | None = None) -> None:
    """Initialize structured logging and global exception handling for the server."""
    level = (log_level or settings.LOG_LEVEL or "INFO").upper()
    json_enabled = settings.LOG_JSON if json_logs is None else json_logs
    _ensure_log_dir(settings.LOG_FILE)

    logging.config.dictConfig(_build_logging_config(level, json_enabled))
    _install_global_exception_hooks()

    logger = logging.getLogger("filesystem_mcp.logging")
    logger.info(
        "Logging initialized",
        extra={
            "log_level": level,
            "json_logs": json_enabled,
            "log_file": settings.LOG_FILE,
            "rotation_max_bytes": settings.LOG_MAX_BYTES,
            "rotation_backup_count": settings.LOG_BACKUP_COUNT,
        },
    )
