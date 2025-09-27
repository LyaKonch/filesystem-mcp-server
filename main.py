import os
import sys
import argparse 
from typing import Any
from pathlib import Path
from typing import List, Optional
from mcp.server.fastmcp import FastMCP, Context
from urllib.parse import urlparse, unquote


# Initialize FastMCP server
mcp = FastMCP("filesystem")

# Global variables
ALLOWEDROOTS: List[Path] = []
CLIENT_SUPPORTS_ROOTS: bool = False

def parse_command_line_args():
    """Parse command line arguments for allowed roots."""
    parser = argparse.ArgumentParser(
        description="MCP Filesystem Server",
        epilog="Example: python main.py /path/to/dir1 /path/to/dir2 --allow-cwd"
    )
    
    parser.add_argument(
        'roots',
        nargs='*',
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
    
    return parser.parse_args()

def initialize_allowed_roots():
    """Initialize allowed roots from command line arguments."""
    global ALLOWEDROOTS
    ALLOWEDROOTS.clear()
    
    args = parse_command_line_args()
    
    # Process command line root arguments
    if args.roots:
        for root_path in args.roots:
            try:
                root = norm_path(root_path)
                if root.exists() and root.is_dir():
                    ALLOWEDROOTS.append(root)
                    print(f"Added allowed root from args: {root}", file=sys.stderr)
                else:
                    print(f"Warning: Root path does not exist or is not a directory: {root}", file=sys.stderr)
            except Exception as e:
                print(f"Error processing root path '{root_path}': {e}", file=sys.stderr)
    
    # --allow-cwd is set, use current directory
    if args.allow_cwd:
        fallback_root = Path.cwd()
        ALLOWEDROOTS.append(fallback_root)
        print(f"Using current working directory as root: {fallback_root}", file=sys.stderr)
    
    # If still no roots, show error
    if not ALLOWEDROOTS:
        print("ERROR: No allowed roots specified!", file=sys.stderr)
        print("Use: python main.py /path/to/dir1 /path/to/dir2", file=sys.stderr)
        print("Or: python main.py --allow-cwd", file=sys.stderr)
        sys.exit(1)
    
    print(f"Initialized {len(ALLOWEDROOTS)} allowed roots", file=sys.stderr)

def uri_to_path(uri: str) -> Path:
    """Convert a file:// URI to a Path object."""
    p = urlparse(uri)
    if p.scheme != "file":
        raise ValueError(f"URI must start with file:// or another scheme but not {p.scheme}")
    return Path(unquote(p.path)).resolve()



def norm_path(p: str) -> Path:
    p = os.path.expanduser(p)
    return Path(p).resolve()

def send_roots_list_request(ctx: Context) -> List[Path]:
    """Request the current list of roots from MCP client."""    
    roots_paths: List[Path] = []
    try:
        # Try to call list_roots - may not be available in all FastMCP versions
        if not hasattr(ctx, 'list_roots'):
            print("Context does not have list_roots method - using fallback", file=sys.stderr)
            return []
            
        root_objects = ctx.list_roots()
        print(f"Received {len(root_objects) if root_objects else 0} roots from client", file=sys.stderr)
        
        if not root_objects:
            print("No roots received from client", file=sys.stderr)
            return []
            
    except Exception as e:
        print(f"Error calling ctx.list_roots(): {e} - using fallback", file=sys.stderr)
        return []
    
    for root in root_objects:
        uri = getattr(root, "uri", None) or root.get("uri") if isinstance(root, dict) else None
        name = getattr(root, "name", None) or root.get("name") if isinstance(root, dict) else None
        
        if not uri:
            continue
        try:
            if uri.startswith("file://"):
                root_path = uri_to_path(uri)
            else:
                root_path = Path(uri).resolve()
            
            roots_paths.append(root_path)
            print(f"Added root from client: {root_path} ({name or 'unnamed'})", file=sys.stderr)
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
        
        roots_info = [f"Client supports roots: {CLIENT_SUPPORTS_ROOTS}"]
        roots_info.append(f"Command line args: {' '.join(sys.argv[1:]) if len(sys.argv) > 1 else 'none'}")
        roots_info.append("")
        
        for i, root in enumerate(current_roots, 1):
            roots_info.append(f"{i}. {root}")
        
        return "Allowed root directories:\n" + "\n".join(roots_info)
    
    except Exception as e:
        return f"Error getting allowed roots: {str(e)}"

@mcp.tool()
async def refresh_roots(ctx: Context) -> str:
    """Manually refresh roots from client (if supported) or environment.
    
    Returns:
        Status of refresh operation
    """
    try:
        if CLIENT_SUPPORTS_ROOTS:
            client_roots = send_roots_list_request(ctx)
            if client_roots:
                global ALLOWEDROOTS
                ALLOWEDROOTS = client_roots
                return f"Refreshed {len(client_roots)} roots from client"
            else:
                return "No roots received from client"
        else:
            initialize_allowed_roots()
            return f"Client doesn't support roots. Using default root: {ALLOWEDROOTS[0] if ALLOWEDROOTS else 'none'}"
    except Exception as e:
        return f"Error refreshing roots: {str(e)}"

@mcp.tool()
async def update_roots(newroots: List[str]) -> str:
    """Update allowed roots from a list of paths.
    
    Args:
        ctx: List of new root paths
    """
    try:
        new_roots = []
        for p in newroots:
            try:
                path_obj = norm_path(p)
                if path_obj.exists() and path_obj.is_dir():
                    new_roots.append(path_obj)
                else:
                    return f"Error: Path '{p}' does not exist or is not a directory"
            except Exception as e:
                return f"Error processing path '{p}': {str(e)}"
        
        if not new_roots:
            return "Error: No valid directories provided"
        
        global ALLOWEDROOTS
        ALLOWEDROOTS = new_roots
        return f"Updated allowed roots to {len(new_roots)} directories"
    
    except Exception as e:
        return f"Error updating roots: {str(e)}"

@mcp.tool()
async def add_roots(newroots: List[str]) -> str:
    """Add allowed roots from a list of paths.

    Args:
        ctx: List of new root paths
    """
    try:
        added_roots = []
        for p in newroots:
            try:
                path_obj = norm_path(p)
                if path_obj.exists() and path_obj.is_dir():
                    if path_obj not in ALLOWEDROOTS:
                        ALLOWEDROOTS.append(path_obj)
                        added_roots.append(path_obj)
                else:
                    return f"Error: Path '{p}' does not exist or is not a directory"
            except Exception as e:
                return f"Error processing path '{p}': {str(e)}"
        
        if not added_roots:
            return "No new valid directories were added"
        
        return f"Added {len(added_roots)} new allowed roots"
    
    except Exception as e:
        return f"Error adding roots: {str(e)}"

if __name__ == "__main__":
    
    # Initialize roots at startup
    initialize_allowed_roots()

    # Run the server
    mcp.run(transport="stdio")
    
    