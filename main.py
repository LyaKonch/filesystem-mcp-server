import os
import sys
from typing import Any
from pathlib import Path
from typing import List, Optional
from mcp.server.fastmcp import FastMCP, Context
from urllib.parse import urlparse, unquote


# Initialize FastMCP server
mcp = FastMCP("filesystem")


ALLOWEDROOTS: List[Path] = []

def initialize_allowed_roots():
    """Initialize allowed roots from environment or default to current directory."""
    global ALLOWEDROOTS
    ALLOWEDROOTS.clear()
    
    # Try to get from environment variable
    env_roots = os.getenv('MCP_ALLOWED_ROOTS') or os.getenv("PROJECT_ROOT")
    if env_roots:
        # this is just in case someone uses commas instead of os.pathsep
        candidates = []
        if os.pathsep in env_roots:
            candidates = env_roots.split(os.pathsep)
        elif "," in env_roots:
            candidates = env_roots.split(",")
        else:
            candidates = [env_roots]
        
        for r in candidates:
            r = r.strip()
            if not r:
                continue
            try:
                if r.startswith("file://"):
                    r = uri_to_path(r)
                else:
                    r = norm_path(r)
                if r.exists():
                    ALLOWEDROOTS.append(r)
                    print(f"Added allowed root from env: {r}", file=sys.stderr)
                else:
                    print(f"Warning: Path from env does not exist: {r}", file=sys.stderr)
            except Exception as e:
                print(f"Error processing path '{r}' from env: {e}", file=sys.stderr)
    
    # If no roots set, use current working directory as fallback
    if not ALLOWEDROOTS:
        fallback_root = Path.cwd()
        ALLOWEDROOTS.append(fallback_root)
        print(f"Using fallback root: {fallback_root}", file=sys.stderr)
    
    print(f"Initialized {len(ALLOWEDROOTS)} allowed roots", file=sys.stderr)

def uri_to_path(uri: str) -> Path:
    """Convert a file:// URI to a Path object."""
    p = urlparse(uri)
    if p.scheme != "file":
        raise ValueError(f"URI must start with file:// or another scheme but not {p.scheme}")
    return Path(unquote(p.path)).resolve()

# Initialize roots at startup
initialize_allowed_roots()

def norm_path(p: str) -> Path:
    p = os.path.expanduser(p)
    return Path(p).resolve()

def send_roots_list_request(ctx: Context) -> List[Path]:
    """Request the current list of roots from MCP client."""
    roots_paths: List[Path] = []
    try:
        # Check if client supports roots by trying to call list_roots
        if not hasattr(ctx, 'list_roots'):
            print("Client does not support roots API", file=sys.stderr)
            return []
            
        root_objects = ctx.list_roots()
        print(f"DEBUG: root_objects from ctx.list_roots(): {root_objects}", file=sys.stderr)
    except Exception as e:
        print(f"Error calling ctx.list_roots(): {e}", file=sys.stderr)
        return []
    
    for root in root_objects:
        uri = getattr(root, "uri", None) or root.get("uri") if isinstance(root, dict) else None
        if not uri:
            continue
        try:
            if uri.startswith("file://"):
                roots_paths.append(uri_to_path(uri))
            else:
                roots_paths.append(Path(uri).resolve())
        except Exception as e:
            print(f"[warning] skipping invalid root URI {uri}: {e}", file=sys.stderr)
    return roots_paths

def get_current_roots(ctx: Optional[Context] = None) -> List[Path]:
    """Get current roots from MCP or fallback."""
    
    if ctx:
        try:
            roots = send_roots_list_request(ctx)
            if roots:
                print(f"Using {len(roots)} roots from client", file=sys.stderr)
                return roots
        except Exception as e:
            print(f"[error] Error getting roots from client: {e}", file=sys.stderr)

    # Fallback to global list
    if ALLOWEDROOTS:
        return ALLOWEDROOTS
    
    # Ultimate fallback
    return [Path.cwd()]

def withinAllowed(path: Path, ctx: Optional[Context] = None) -> bool:
    """Check if a given path is within allowed roots."""
    current_roots = get_current_roots(ctx)
    if not current_roots:
        return False
    
    p = path.resolve()
    for root in current_roots:
        try:
            # Check if path is within the root
            p.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False



@mcp.tool()
async def list_files(path: str, ctx: Context) -> str:
    """List files and directories at the given path.
    
    Args:
        path: Path to list contents of
    """
    try:
        target_path = norm_path(path)
        
        if not withinAllowed(target_path, ctx):
            return f"Error: Path '{path}' is not within allowed roots"
        
        if not target_path.exists():
            return f"Error: Path '{path}' does not exist"
        
        if not target_path.is_dir():
            return f"Error: Path '{path}' is not a directory"
        
        items = []
        for item in target_path.iterdir():
            if item.is_dir():
                items.append(f"📁 {item.name}/")
            else:
                items.append(f"📄 {item.name}")
        
        if not items:
            return f"Directory '{path}' is empty"
        
        return f"Contents of '{path}':\n" + "\n".join(sorted(items))
    
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
async def read_file(path: str, ctx: Context) -> str:
    """Read the contents of a file.
    
    Args:
        path: Path to the file to read
    """
    try:
        target_path = norm_path(path)
        
        if not withinAllowed(target_path, ctx):
            return f"Error: Path '{path}' is not within allowed roots"
        
        if not target_path.exists():
            return f"Error: File '{path}' does not exist"
        
        if not target_path.is_file():
            return f"Error: Path '{path}' is not a file"
        
        # Read file contents
        content = target_path.read_text(encoding='utf-8')
        return f"Contents of '{path}':\n\n{content}"
    
    except UnicodeDecodeError:
        return f"Error: File '{path}' contains binary data or unsupported encoding"
    except Exception as e:
        return f"Error reading file: {str(e)}"

@mcp.tool() 
async def write_file(path: str, content: str, ctx: Context) -> str:
    """Write content to a file.
    
    Args:
        path: Path to the file to write
        content: Content to write to the file
    """
    try:
        target_path = norm_path(path)
        
        if not withinAllowed(target_path, ctx):
            return f"Error: Path '{path}' is not within allowed roots"
        
        # Create parent directories if they don't exist
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write content to file
        target_path.write_text(content, encoding='utf-8')
        return f"Successfully wrote {len(content)} characters to '{path}'"
    
    except Exception as e:
        return f"Error writing file: {str(e)}"

@mcp.tool()
async def get_allowed_roots(ctx: Context) -> str:
    """Get the list of currently allowed root directories.
    
    Returns:
        List of allowed root directories
    """
    try:
        current_roots = get_current_roots(ctx)
        if not current_roots:
            return "No allowed roots configured"
        
        roots_info = []
        for i, root in enumerate(current_roots, 1):
            roots_info.append(f"{i}. {root}")
        
        return "Allowed root directories:\n" + "\n".join(roots_info)
    
    except Exception as e:
        return f"Error getting allowed roots: {str(e)}"



if __name__ == "__main__":
    # Run the server
    mcp.run(transport="stdio")