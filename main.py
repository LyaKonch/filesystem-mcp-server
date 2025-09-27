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

@mcp.tool()
async def create_directory(path: str, ctx: Context) -> str:
    """Create a new directory or ensure a directory exists.
    
    Args:
        path: Path to the directory to create
    """
    try:
        target_path = norm_path(path)
        
        if not withinAllowed(target_path, ctx):
            return f"Error: Path '{path}' is not within allowed roots"
        
        target_path.mkdir(parents=True, exist_ok=True) 
        return f"Successfully created directory '{path}'"
    
    except Exception as e:
        return f"Error creating directory: {str(e)}"

@mcp.tool()
async def list_directory_with_sizes(path: str, sort_by: str = "name", ctx: Context = None) -> str:
    """Get a detailed listing of files and directories with sizes.
    
    Args:
        path: Path to list contents of
        sort_by: Sort by 'name' or 'size' (default: name)
    """
    try:
        target_path = norm_path(path)
        
        if not withinAllowed(target_path, ctx):
            return f"Error: Path '{path}' is not within allowed roots"
        
        if not target_path.exists():
            return f"Error: Path '{path}' does not exist"
        
        if not target_path.is_dir():
            return f"Error: Path '{path}' is not a directory"
        
        entries = []
        total_size = 0
        total_files = 0
        total_dirs = 0
        
        for item in target_path.iterdir():
            try:
                stats = item.stat()
                size = stats.st_size
                is_dir = item.is_dir()
                
                if is_dir:
                    total_dirs += 1
                    size_str = ""
                else:
                    total_files += 1
                    total_size += size
                    size_str = format_size(size)
                
                entries.append({
                    'name': item.name,
                    'is_dir': is_dir,
                    'size': size,
                    'size_str': size_str
                })
            except Exception:
                # Skip files we can't stat
                continue
        
        # Sort entries
        if sort_by == "size":
            entries.sort(key=lambda x: x['size'], reverse=True)
        else:
            entries.sort(key=lambda x: x['name'].lower())
        
        # Format output
        lines = [f"Contents of '{path}':\n"]
        for entry in entries:
            prefix = "📁" if entry['is_dir'] else "📄"
            name = f"{entry['name']}/" if entry['is_dir'] else entry['name']
            size = entry['size_str'].rjust(10) if entry['size_str'] else ""
            lines.append(f"{prefix} {name:<30} {size}")
        
        # Add summary
        lines.append("")
        lines.append(f"Total: {total_files} files, {total_dirs} directories")
        lines.append(f"Combined size: {format_size(total_size)}")
        
        return "\n".join(lines)
    
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
async def get_file_info(path: str, ctx: Context) -> str:
    """Get detailed metadata about a file or directory.
    
    Args:
        path: Path to the file or directory
    """
    try:
        target_path = norm_path(path)
        
        if not withinAllowed(target_path, ctx):
            return f"Error: Path '{path}' is not within allowed roots"
        
        if not target_path.exists():
            return f"Error: Path '{path}' does not exist"
        
        stats = target_path.stat()
        
        info = [
            f"Path: {target_path}",
            f"Name: {target_path.name}",
            f"Type: {'Directory' if target_path.is_dir() else 'File'}",
            f"Size: {format_size(stats.st_size)}",
            f"Modified: {format_timestamp(stats.st_mtime)}",
            f"Created: {format_timestamp(stats.st_ctime)}",
            f"Permissions: {oct(stats.st_mode)[-3:]}",
        ]
        
        if target_path.is_file():
            # Add file-specific info
            try:
                with open(target_path, 'rb') as f:
                    first_bytes = f.read(100)
                    is_binary = b'\x00' in first_bytes
                info.append(f"Binary: {'Yes' if is_binary else 'No'}")
                
                if not is_binary and target_path.suffix:
                    info.append(f"Extension: {target_path.suffix}")
                    
            except Exception:
                pass
        
        elif target_path.is_dir():
            # Add directory-specific info
            try:
                item_count = len(list(target_path.iterdir()))
                info.append(f"Items: {item_count}")
            except Exception:
                pass
        
        return "\n".join(info)
    
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
async def move_file(source: str, destination: str, ctx: Context) -> str:
    """Move or rename files and directories.
    
    Args:
        source: Source path
        destination: Destination path
    """
    try:
        source_path = norm_path(source)
        dest_path = norm_path(destination)
        
        if not withinAllowed(source_path, ctx):
            return f"Error: Source path '{source}' is not within allowed roots"
        
        if not withinAllowed(dest_path, ctx):
            return f"Error: Destination path '{destination}' is not within allowed roots"
        
        if not source_path.exists():
            return f"Error: Source '{source}' does not exist"
        
        if dest_path.exists():
            return f"Error: Destination '{destination}' already exists"
        
        # Create parent directories if needed
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        source_path.rename(dest_path)
        return f"Successfully moved '{source}' to '{destination}'"
    
    except Exception as e:
        return f"Error moving file: {str(e)}"

@mcp.tool()
async def search_files(path: str, pattern: str, ctx: Context, exclude_patterns: List[str] = None) -> str:
    """Search for files matching a pattern.
    
    Args:
        path: Directory to search in
        pattern: Glob pattern to match (e.g., '*.py', '**/*.txt')
        exclude_patterns: Optional list of patterns to exclude
    """
    try:
        import fnmatch
        
        search_path = norm_path(path)
        
        if not withinAllowed(search_path, ctx):
            return f"Error: Path '{path}' is not within allowed roots"
        
        if not search_path.exists():
            return f"Error: Path '{path}' does not exist"
        
        if not search_path.is_dir():
            return f"Error: Path '{path}' is not a directory"
        
        if exclude_patterns is None:
            exclude_patterns = []
        
        matches = []
        
        # Use ** for recursive search
        if '**' in pattern:
            for file_path in search_path.rglob(pattern.replace('**/', '')):
                if should_include_file(file_path, search_path, exclude_patterns):
                    matches.append(str(file_path))
        else:
            for file_path in search_path.glob(pattern):
                if should_include_file(file_path, search_path, exclude_patterns):
                    matches.append(str(file_path))
        
        if not matches:
            return f"No files found matching pattern '{pattern}' in '{path}'"
        
        matches.sort()
        result = f"Found {len(matches)} files matching '{pattern}':\n"
        result += "\n".join(matches)
        
        return result
    
    except Exception as e:
        return f"Error searching files: {str(e)}"

@mcp.tool()
async def read_multiple_files(paths: List[str], ctx: Context) -> str:
    """Read contents of multiple files simultaneously.
    
    Args:
        paths: List of file paths to read
    """
    try:
        if not paths:
            return "Error: No file paths provided"
        
        results = []
        
        for file_path in paths:
            try:
                target_path = norm_path(file_path)
                
                if not withinAllowed(target_path, ctx):
                    results.append(f"{file_path}: Error - Path not within allowed roots")
                    continue
                
                if not target_path.exists():
                    results.append(f"{file_path}: Error - File does not exist")
                    continue
                
                if not target_path.is_file():
                    results.append(f"{file_path}: Error - Not a file")
                    continue
                
                content = target_path.read_text(encoding='utf-8')
                results.append(f"{file_path}:\n{content}")
                
            except UnicodeDecodeError:
                results.append(f"{file_path}: Error - Binary file or unsupported encoding")
            except Exception as e:
                results.append(f"{file_path}: Error - {str(e)}")
        
        return "\n---\n".join(results)
    
    except Exception as e:
        return f"Error reading multiple files: {str(e)}"

# Helper functions
def format_size(size: int) -> str:
    """Format file size in human readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"

def format_timestamp(timestamp: float) -> str:
    """Format timestamp to readable string."""
    from datetime import datetime
    return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')

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

if __name__ == "__main__":
    
    # Initialize roots at startup
    initialize_allowed_roots()

    # Run the server
    mcp.run(transport="stdio")
    
    