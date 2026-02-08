from argparse import ArgumentParser
import os
from pathlib import Path
from fastmcp import FastMCP, Context 

import logging

import utilities.dependencies as dependencies

from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

from utilities.logging import initialize_logging

mcp = FastMCP("filesystem")

def parse_command_line_args():
    """Parse command line arguments for allowed roots."""
    parser = ArgumentParser(
        description="MCP Filesystem Server",
        epilog="Example: python main.py /path/to/dir1 /path/to/dir2 --allow-cwd --transport sse/http"
    )
    
    parser.add_argument(
        '--roots',
        nargs='*',
        type=Path,
        help='Allowed root directories (can specify multiple)'
    )
    
    parser.add_argument(
        '--allow-cwd',
        action='store_true',
        help='Allow access to current working directory if no roots specified'
    )
    
    parser.add_argument(
        '--recursive',
        action='store_true',
        default=True,
        help='Allow access to subdirectories within roots (default: True)'
    )
    
    parser.add_argument(
        '--transport', 
        nargs=1, 
        type=str, 
        help="transport method for the server. stdio/sse/http"
    )

    args = parser.parse_args()
    if args.allow_cwd:
        args.roots = args.roots + [Path(os.getcwd())] if args.roots else [Path(os.getcwd())]
    if args.roots is None and args.allow_cwd:
        args.roots = [Path(os.getcwd())]
    if args.transport is not None:
        dependencies.TRANSPORT = args.transport[0]
    dependencies.GLOBAL_ROOTS = list(map(dependencies.check_path, args.roots))
    dependencies.logger.info(f"Configured roots: {dependencies.GLOBAL_ROOTS}")

    return parser.parse_args()


if __name__ == "__main__":
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler("debug.log"),
        ]
    )

    parse_command_line_args()
    initialize_logging()
    
    # Import and register system monitoring tools
    import systemmonitoring
    systemmonitoring._init_systemmonitoring(dependencies.logger, dependencies.check_path, dependencies.withinAllowed)
    systemmonitoring.register_tools(mcp)

    asgi_middlewares = [
        Middleware(CORSMiddleware,allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    ]

    import os
    # default localhost, if not specified in env
    host = os.environ.get("MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("MCP_PORT", 8000))

    # Run the server
    mcp.run(transport=dependencies.TRANSPORT, host=host, port=port)
