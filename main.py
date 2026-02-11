from argparse import ArgumentParser
from pathlib import Path
from fastmcp import FastMCP
from auth.auth import get_auth_provider
from config import settings

from tools import filesystem, monitoring, server_management
import utilities.dependencies as dependencies

from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

from utilities.logging import initialize_logging


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
        help="Host to bind (for SSE)")
    parser.add_argument(
        "--port", 
        type=int, 
        help="Port to bind (for SSE)")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode with verbose logging",
    )


    parser.add_argument(
        "--no-auth", action="store_true", help="Disable authentication entirely"
    )

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
        valid_roots = [
            dependencies.check_path(r, check_existence=True) for r in args.roots
        ]
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

    dependencies.logger.info(f"Configured roots: {settings.ALLOWED_ROOTS}")

    if args.no_auth or args.transport == "stdio":
        settings.AUTH_ENABLED = False

    if args.persist:
        settings.USE_PERSISTENT_STORAGE = True

    if args.redis:
        settings.USE_REDIS = True
        settings.USE_PERSISTENT_STORAGE = True

    return args


if __name__ == "__main__":
    parse_command_line_args()
    initialize_logging()

    auth_provider = get_auth_provider()

    mcp = FastMCP(
        name="Filesystem & Monitor",
        instructions="Secure filesystem access and system monitoring.",
        auth=auth_provider,
    )

    filesystem.register(mcp)
    server_management.register(mcp)
    monitoring.register(mcp)

    # for testing purposes
    import tests.systemmonitoring as systemmonitoring

    systemmonitoring._init_systemmonitoring(
        dependencies.logger, dependencies.check_path, dependencies.withinAllowed
    )
    systemmonitoring.register_tools(mcp)

    asgi_middlewares = [
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
    ]

    dependencies.logger.info(
        f"Starting Server | Transport: {settings.TRANSPORT} | Auth: {settings.AUTH_ENABLED}"
    )
    if settings.TRANSPORT != "stdio":
        dependencies.logger.info(f"Listening on {settings.MCP_HOST}:{settings.MCP_PORT}")
    # here it enters the loop
    mcp.run(
        transport=settings.TRANSPORT,
        host=settings.MCP_HOST,
        port=settings.MCP_PORT,
        middleware=asgi_middlewares,
    )
