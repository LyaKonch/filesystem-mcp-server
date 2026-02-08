import logging
from typing import Literal, Optional, List
import os
import fastmcp
from pathlib import Path
from mcp import ServerSession
from mcp.types import ClientCapabilities, ElicitationCapability, RootsCapability, SamplingCapability
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

def check_path(value:Path | str, check_existence: bool = True) -> Path:
    try:
        # explicitly converts it to Path 
        if isinstance(value, str):
            value = Path(value)

        value = Path(os.path.expanduser(value)).resolve()

        if check_existence and not value.exists():
            raise ValueError(f"Error: Path '{value}' does not exist")
    
        return value
            
    except (TypeError, ValueError, OSError) as exc:
        logger.error(f"Invalid path specified: {value}", exc_info=exc)
        raise

async def validate_path(path_str: str, 
    ctx: fastmcp.Context, 
    must_exist:bool = True, 
    expected_type: Optional[Literal['file','dir']]='None'
) -> Path:
    """Validate a path string and return a Path object if valid, otherwise raise an error."""
    # a bit strange to set ceck_existance to false, but i want to control exceptions here not within inner function
    path = check_path(path_str, check_existence=False)
    
    if not await withinAllowed(path, ctx):
        raise ValueError(f"Access denied: Path '{path}' is not within allowed roots.")
    
    if must_exist and not path.exists():
        raise ValueError(f"Error: Path '{path}' does not exist")
    
    if must_exist and expected_type:
        if expected_type == 'file' and not path.is_file():
            raise ValueError(f"Error: Expected file, but '{path.name}' is a directory")
        
        if expected_type == 'dir' and not path.is_dir():
            raise ValueError(f"Error: Expected directory, but '{path.name}' is a file")
    
    return path

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

def checkElicitationCapability(session: ServerSession) -> bool:
    caps = ClientCapabilities(elicitation=ElicitationCapability())
    return session.check_client_capability(caps)

def checkSamplingCapability(session: ServerSession) -> bool:
    caps = ClientCapabilities(sampling=SamplingCapability())
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

## Helper functions------
def format_timestamp(timestamp: float) -> str:
    """Format timestamp to readable string."""
    from datetime import datetime
    return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')


def format_size(size: int) -> str:
    """Format file size in human readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"



def should_include_file(file_path: Path, base_path: Path, exclude_patterns: List[str]) -> bool:
    """Check if file should be included based on exclude patterns."""
    import fnmatch
    
    try:
        # Get relative path for pattern matching
        rel_path = file_path.relative_to(base_path)
        rel_path_str = str(rel_path).replace('\\', '/')
        
        for pattern in exclude_patterns:
            if fnmatch.fnmatch(rel_path_str, pattern):
                return False
            # Also check just the filename
            if fnmatch.fnmatch(file_path.name, pattern):
                return False
    except Exception:
        pass
    
    return True