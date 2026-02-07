import logging
from typing import Any, Literal
import fastmcp
from fastmcp.utilities.logging import configure_logging
import uvicorn

LOG_FILENAME = "fastmcp.log"
FILE_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"

file_handler = logging.FileHandler(LOG_FILENAME, encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(FILE_FORMAT))


def patch_uvicorn_config():
    # formatter
    uvicorn.config.LOGGING_CONFIG["formatters"]["file_fmt"] = {
        "format": FILE_FORMAT,
        "datefmt": "%Y-%m-%d %H:%M:%S",
    }
    # uvicorn logger config
    uvicorn.config.LOGGING_CONFIG["handlers"]["file"] = {
        "class": "logging.FileHandler",
        "filename": LOG_FILENAME,
        "mode": "a",
        "encoding": "utf-8",
        "formatter": "file_fmt",
    }
    
    for logger_name in ["uvicorn", "uvicorn.error", "uvicorn.access"]:
        if logger_name in uvicorn.config.LOGGING_CONFIG["loggers"]:
            handlers = uvicorn.config.LOGGING_CONFIG["loggers"][logger_name].get("handlers", [])
            if "file" not in handlers:
                handlers.append("file")
                uvicorn.config.LOGGING_CONFIG["loggers"][logger_name]["handlers"] = handlers

def patched_configure_logging(
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] | int = "INFO",
    logger: logging.Logger | None = None,
    enable_rich_tracebacks: bool | None = None,
    **rich_kwargs: Any,
) -> None:
    configure_logging(level=level, logger=logger, enable_rich_tracebacks=enable_rich_tracebacks, **rich_kwargs)
    
    loggers_to_capture = ["fastmcp", "mcp", "uvicorn", "uvicorn.error", "uvicorn.access", "asyncio"]

    for logger in loggers_to_capture:
        target_logger = logging.getLogger(logger)

        has_same_file_handler = any(isinstance(h, logging.FileHandler) 
                                and getattr(h, 'baseFilename', None) == file_handler.baseFilename
                                for h in target_logger.handlers)
        if not has_same_file_handler:
            target_logger.addHandler(file_handler)
        target_logger.setLevel(logging.DEBUG)



def initialize_logging():
    # ovveride uvicorn logging configuration
    patch_uvicorn_config()
    
    # patch fastmcp logging configuration because all handlers are automatically cleared by starting server and i add them manually here for proper logging
    fastmcp.utilities.logging.configure_logging = patched_configure_logging