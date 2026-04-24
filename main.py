import logging
from argparse import ArgumentParser
from pathlib import Path
from typing import Literal, cast

from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

from auth.auth import get_auth_provider
from auth.auth_middleware import create_auth_middleware
from config import settings
from tools import file_transfer, filesystem, monitoring, server_management
from utilities import dependencies
from utilities.logging import initialize_logging, log_exception_with_id


def parse_command_line_args():
    """Parse command line arguments for MCP server configuration."""
    parser = ArgumentParser(
        description="MCP Filesystem Server",
        epilog="Example: python main.py /path/to/dir1 /path/to/dir2 --allow-cwd --transport sse/http",
    )

    parser.add_argument(
        "--roots",
        nargs="*",
        type=Path,
        help="Allowed root directories (can specify multiple)",
    )

    parser.add_argument(
        "--allow-cwd",
        action="store_true",
        help="Allow access to current working directory if no roots specified",
    )

    parser.add_argument(
        "--recursive",
        action="store_true",
        default=True,
        help="Allow access to subdirectories within roots (default: True)",
    )

    parser.add_argument(
        "--transport",
        type=str,
        help="transport method for the server. stdio/sse/http",
    )
    parser.add_argument(
        "--host",
        type=str,
        help="Host to bind (for SSE)",
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Port to bind (for SSE)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode with verbose logging",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Minimal logging level (overrides LOG_LEVEL env variable)",
    )
    parser.add_argument(
        "--log-json",
        action="store_true",
        help="Enable JSON log format for console and file handlers",
    )

    parser.add_argument("--no-auth", action="store_true", help="Disable authentication entirely")

    parser.add_argument(
        "--persist",
        action="store_true",
        help="Enable persistent storage (requires keys in .env)",
    )
    parser.add_argument(
        "--redis",
        action="store_true",
        help="Use Redis instead of Disk (requires --persist)",
    )

    args = parser.parse_args()
    if args.roots:
        valid_roots = [dependencies.check_path(r, check_existence=True) for r in args.roots]
        settings.ALLOWED_ROOTS.extend(valid_roots)
    if args.allow_cwd:
        settings.ALLOW_CWD = True
        settings.ALLOWED_ROOTS.append(Path.cwd())

    if args.transport:
        settings.TRANSPORT = args.transport
    if args.host:
        settings.MCP_HOST = args.host
    if args.port:
        settings.MCP_PORT = args.port

    if args.log_level:
        settings.LOG_LEVEL = args.log_level.upper()
    if args.log_json:
        settings.LOG_JSON = True

    if args.no_auth or args.transport == "stdio":
        settings.AUTH_ENABLED = False

    if args.persist:
        settings.USE_PERSISTENT_STORAGE = True

    if args.redis:
        settings.USE_REDIS = True
        settings.USE_PERSISTENT_STORAGE = True

    return args


if __name__ == "__main__":
    args = parse_command_line_args()

    if args.debug:
        settings.DEBUG = True
        settings.LOG_LEVEL = "DEBUG"

    initialize_logging(settings.LOG_LEVEL, settings.LOG_JSON)
    logger = logging.getLogger("filesystem_mcp.main")

    logger.info(
        "Application startup",
        extra={
            "transport": settings.TRANSPORT,
            "host": settings.MCP_HOST,
            "port": settings.MCP_PORT,
            "auth_enabled": settings.AUTH_ENABLED,
        },
    )
    logger.info("Configured roots: %s", settings.ALLOWED_ROOTS)

    auth_provider = get_auth_provider()
    if settings.AUTH_ENABLED and auth_provider is None:
        logger.warning("Auth is enabled but auth provider failed to initialize; disabling auth")
        settings.AUTH_ENABLED = False

    mcp = FastMCP(
        name="Filesystem & Monitor",
        instructions="Secure filesystem access and system monitoring.",
        auth=auth_provider,
    )

    authmiddleware = create_auth_middleware()
    mcp.add_middleware(authmiddleware)
    logger.info("Auth middleware registered")

    file_transfer.ft_register_routes(mcp)
    filesystem.register(mcp)
    server_management.register(mcp)
    monitoring.register(mcp)

    asgi_middlewares = [
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
    ]

    logger.info(
        "Starting Server | Transport: %s | Auth: %s",
        settings.TRANSPORT,
        settings.AUTH_ENABLED,
    )
    if settings.TRANSPORT != "stdio":
        logger.info("Listening on %s:%s", settings.MCP_HOST, settings.MCP_PORT)
    try:
        # here it enters the loop
        if settings.TRANSPORT == "stdio":
            mcp.run(
                transport=cast(Literal["stdio"], settings.TRANSPORT),
            )
        else:
            mcp.run(
                transport=cast(
                    Literal["stdio", "http", "sse", "streamable-http"], settings.TRANSPORT
                ),
                host=settings.MCP_HOST,
                port=settings.MCP_PORT,
                middleware=asgi_middlewares,
            )
    except Exception as exc:
        error_id = log_exception_with_id(
            logger,
            "Fatal server error",
            exc,
            transport=settings.TRANSPORT,
            host=settings.MCP_HOST,
            port=settings.MCP_PORT,
        )
        logger.error("Server terminated with fatal error_id=%s", error_id)
        raise
    finally:
        logger.info("Application shutdown")
