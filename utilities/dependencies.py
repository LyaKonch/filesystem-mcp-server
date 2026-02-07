import logging
import os
import fastmcp
from pathlib import Path
from mcp import RootsCapability, ServerSession
from mcp.types import ClientCapabilities
from fastmcp.server.middleware import MiddlewareContext
from urllib.parse import urlparse, unquote

GLOBAL_ROOTS: list[Path] = []
TRANSPORT = "sse"
logger = logging.getLogger("fastmcp")

async def get_combined_roots(context: fastmcp.Context) -> list[Path]:
    result_list: list[Path] = []
    if GLOBAL_ROOTS is not None:
        result_list = [p for p in GLOBAL_ROOTS]
    if checkRootsCapability(context.session):
        clients_roots = await fetch_roots_from_client(context)
        if clients_roots is not None:
            clients_roots_checked = [check_path(p) for p in clients_roots]
            result_list.extend(clients_roots_checked)
    return result_list

# def convert_roots_to_str() -> list[Path]:
#     ROOTS_STR: dict[str, list[Path]] = {
#         "command_line": [],
#         "client_roots": [],
#         "config_file": []
#     }
#     for key, roots_list in ROOTS.items():
#         ROOTS_STR[key] = [str(root) for root in roots_list] if len(roots_list) > 0 else ""
#     return ROOTS_STR

def uri_to_path(uri: str) -> Path:
    """Convert a file:// URI to a Path object."""
    p = urlparse(uri)
    if p.scheme != "file":
        raise ValueError(f"URI must start with file:// or another scheme but not {p.scheme}")
    file = Path(unquote(p.path))
    return check_path(file)

def check_path(value:Path) -> Path:
    try:
        value = Path(os.path.expanduser(value)).resolve()

        if not value.exists():
            raise ValueError(f"Error: Path '{value}' does not exist")
        
        if not value.is_dir():
            raise ValueError(f"Error: Path '{value}' is not a directory")
        
        return value
            
    except (TypeError, ValueError, OSError) as exc:
        logger.error(f"Invalid path specified: {value}", exc_info=exc)
        raise

async def fetch_roots_from_client(context: MiddlewareContext):
    if checkRootsCapability(context.session):
        logger.info("Listing roots from client")
        roots = None
        if context.fastmcp_context:
            try:
                roots = await context.fastmcp_context.list_roots()
                uris: list[Path] = []
                if roots is not None:
                    for root in roots:
                        file_url = uri_to_path(str(root.uri))
                        uris.append(file_url)
                    logger.info(f"Fetched roots from client: {uris}")
                    return uris
                else:
                    logger.debug("No roots available from client")
            except Exception as e:
                logger.error(f"Error fetching roots from client: {e}")

def checkRootsCapability(session: ServerSession) -> bool:
    caps = ClientCapabilities(roots=RootsCapability())
    return session.check_client_capability(caps)


async def withinAllowed(path: Path, ctx: fastmcp.Context) -> bool:
    """Check if a given path is within allowed scopes of Global allowed directories on server and roots from client."""
    current_scope= await get_combined_roots(ctx)
    
    p = check_path(path)
    for root in current_scope:
        try:
            # Check if path is within the root
            p.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False



