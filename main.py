import os
import sys
import argparse 
from typing import Any
from pathlib import Path
from typing import List, Optional
from fastmcp import FastMCP, Context 
from fastmcp.utilities.logging import get_logger, configure_logging
from urllib.parse import urlparse, unquote
import shutil
import asyncio

# --- Global Configuration ---

# Configure FastMCP logging properly
logger = get_logger(__name__)
configure_logging(level="INFO")

# Store paths passed via command line at startup
CMD_LINE_ROOTS: List[Path] = []

# --- MCP Server Initialization ---
mcp = FastMCP("filesystem")

# --- Tools ---

@mcp.tool()
async def get_client_features(ctx: Context) -> dict:
    """Get information about which features the client supports."""
    logger.info("Checking client capabilities")
    
    features = {
        "elicitation": False,
        "sampling": False,
        "roots": False,
    }
    
    # Check capabilities using session
    try:
        from mcp.types import ClientCapabilities, ElicitationCapability
        elicitation_cap = ClientCapabilities(elicitation=ElicitationCapability())
        features["elicitation"] = ctx.session.check_client_capability(elicitation_cap)
    except Exception as e:
        logger.warning(f"Error checking elicitation capability: {e}")
        features["elicitation"] = False
    
    try:
        from mcp.types import ClientCapabilities, SamplingCapability
        sampling_cap = ClientCapabilities(sampling=SamplingCapability())
        features["sampling"] = ctx.session.check_client_capability(sampling_cap)
    except Exception as e:
        logger.warning(f"Error checking sampling capability: {e}")
        features["sampling"] = False
    
    try:
        from mcp.types import ClientCapabilities, RootsCapability
        roots_cap = ClientCapabilities(roots=RootsCapability())
        features["roots"] = ctx.session.check_client_capability(roots_cap)
    except Exception as e:
        logger.warning(f"Error checking roots capability: {e}")
        features["roots"] = False
    
    # Try to get client roots if supported
    client_roots_list = []
    if features["roots"]:
        try:
            roots_result = await ctx.list_roots()
            if roots_result:
                for root in roots_result:
                    uri = root.uri
                    if uri.startswith("file://"):
                        root_path = uri_to_path(uri)
                        client_roots_list.append(str(root_path))
                        logger.info(f"Found client root: {root_path}")
        except Exception as e:
            logger.warning(f"Error getting client roots: {e}")
            
    return {
        "features": features,
        "client_roots": client_roots_list,
        "command_line_roots": [str(path) for path in CMD_LINE_ROOTS]
    }


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
    global CMD_LINE_ROOTS
    CMD_LINE_ROOTS.clear()
    
    args = parse_command_line_args()
    
    # Process command line root arguments
    if args.roots:
        for root_path in args.roots:
            try:
                root = norm_path(root_path)
                if root.exists() and root.is_dir():
                    CMD_LINE_ROOTS.append(root)
                    logger.info(f"Added allowed root from args: {root}")
                else:
                    logger.warning(f"Root path does not exist or is not a directory: {root}")
            except Exception as e:
                logger.error(f"Error processing root path '{root_path}': {e}")
    
    # --allow-cwd is set, use current directory
    if args.allow_cwd:
        fallback_root = Path.cwd()
        CMD_LINE_ROOTS.append(fallback_root)
        logger.info(f"Using current working directory as root: {fallback_root}")
    
    # If still no roots, show error
    if not CMD_LINE_ROOTS:
        logger.error("No allowed roots specified!")
        logger.error("Use: python main.py /path/to/dir1 /path/to/dir2")
        logger.error("Or: python main.py --allow-cwd")
        sys.exit(1)
    
    logger.info(f"Initialized {len(CMD_LINE_ROOTS)} allowed roots")

def uri_to_path(uri: str) -> Path:
    """Convert a file:// URI to a Path object."""
    p = urlparse(uri)
    if p.scheme != "file":
        raise ValueError(f"URI must start with file:// or another scheme but not {p.scheme}")
    return Path(unquote(p.path)).resolve()



def norm_path(p: str) -> Path:
    p = os.path.expanduser(p)
    return Path(p).resolve()

async def send_roots_list_request(ctx: Context) -> List[Path]:
    """Request the current list of roots from MCP client."""    
    roots_paths: List[Path] = []
    try:
        # Try to call list_roots - may not be available in all FastMCP versions
        if not hasattr(ctx, 'list_roots'):
            logger.warning("Context does not have list_roots method - using fallback")
            return []
            
        root_objects = await ctx.list_roots()  # Added await here
        logger.info(f"Received {len(root_objects) if root_objects else 0} roots from client")
        
        if not root_objects:
            logger.info("No roots received from client")
            return []
            
    except Exception as e:
        logger.error(f"Error calling ctx.list_roots(): {e} - using fallback")
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
            logger.info(f"Added root from client: {root_path} ({name or 'unnamed'})")
        except Exception as e:
            logger.warning(f"Skipping invalid root URI {uri}: {e}")
    
    return roots_paths

def get_current_roots(ctx: Optional[Context] = None) -> List[Path]:
    """Get current roots from MCP or fallback."""
    
    if ctx:
        try:
            # This is async function, can't call from sync context easily
            # Better to use async version
            logger.warning("get_current_roots called with context - use async version instead")
        except Exception as e:
            logger.error(f"Error getting roots from client: {e}")

    # Fallback to command line roots
    if CMD_LINE_ROOTS:
        return CMD_LINE_ROOTS
    
    # Ultimate fallback
    return [Path.cwd()]

async def get_current_roots_async(ctx: Context) -> List[Path]:
    """Async version to get current roots from MCP or fallback."""
    combined_roots = list(CMD_LINE_ROOTS)  # Start with command line roots
    
    try:
        # Check if client supports roots
        from mcp.types import ClientCapabilities, RootsCapability
        roots_cap = ClientCapabilities(roots=RootsCapability())
        if ctx.session.check_client_capability(roots_cap):
            client_roots = await send_roots_list_request(ctx)
            combined_roots.extend(client_roots)
            logger.info(f"Combined {len(CMD_LINE_ROOTS)} command line roots with {len(client_roots)} client roots")
        else:
            logger.info("Client does not support roots, using command line roots only")
    except Exception as e:
        logger.warning(f"Error getting client roots: {e}")
    
    # Remove duplicates while preserving order
    seen = set()
    unique_roots = []
    for root in combined_roots:
        if root not in seen:
            seen.add(root)
            unique_roots.append(root)
    
    return unique_roots if unique_roots else [Path.cwd()]

async def withinAllowed(path: Path, ctx: Context) -> bool:
    """Check if a given path is within allowed roots."""
    current_roots = await get_current_roots_async(ctx)
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
        
        if not await withinAllowed(target_path, ctx):
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
        
        if not await withinAllowed(target_path, ctx):
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
        
        if not await withinAllowed(target_path, ctx):
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
        current_roots = await get_current_roots_async(ctx)
        if not current_roots:
            return "No allowed roots configured"
        
        # Check capabilities
        from mcp.types import ClientCapabilities, RootsCapability
        roots_cap = ClientCapabilities(roots=RootsCapability())
        supports_roots = ctx.session.check_client_capability(roots_cap)
        
        roots_info = [f"Client supports roots: {supports_roots}"]
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
        # Check if client supports roots
        from mcp.types import ClientCapabilities, RootsCapability
        roots_cap = ClientCapabilities(roots=RootsCapability())
        supports_roots = ctx.session.check_client_capability(roots_cap)
        
        if supports_roots:
            client_roots = await send_roots_list_request(ctx)
            if client_roots:
                global CMD_LINE_ROOTS
                CMD_LINE_ROOTS.extend(client_roots)
                # Remove duplicates
                CMD_LINE_ROOTS = list(dict.fromkeys(CMD_LINE_ROOTS))
                return f"Refreshed {len(client_roots)} roots from client, total: {len(CMD_LINE_ROOTS)}"
            else:
                return "No roots received from client"
        else:
            return f"Client doesn't support roots. Using command line roots: {len(CMD_LINE_ROOTS)}"
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
        
        global CMD_LINE_ROOTS
        CMD_LINE_ROOTS = new_roots
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
                    if path_obj not in CMD_LINE_ROOTS:
                        CMD_LINE_ROOTS.append(path_obj)
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
        
        if not await withinAllowed(target_path, ctx):
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

@mcp.tool()
async def delete_file(path: str, ctx: Context) -> str:
    """Delete a file.
    
    Args:
        path: Path to the file to delete
    """
    try:
        target_path = norm_path(path)
        
        if not withinAllowed(target_path, ctx):
            return f"Error: Path '{path}' is not within allowed roots"
        
        if not target_path.exists():
            return f"Error: File '{path}' does not exist"
        
        if not target_path.is_file():
            return f"Error: Path '{path}' is not a file"
        
        target_path.unlink()
        return f"Successfully deleted file '{path}'"
    
    except Exception as e:
        return f"Error deleting file: {str(e)}"

@mcp.tool()
async def delete_directory(path: str, force: bool = False, ctx: Context = None) -> str:
    """Delete a directory. By default, it only deletes empty directories.
    
    Args:
        path: Path to the directory to delete.
        force: If true, deletes the directory and all its contents.
        ctx: The context object.
    """
    try:
        target_path = norm_path(path)

        if not withinAllowed(target_path, ctx):
            return f"Error: Path '{path}' is not within allowed roots"

        if not target_path.exists():
            return f"Error: Directory '{path}' does not exist"

        if not target_path.is_dir():
            return f"Error: Path '{path}' is not a directory"

        if any(target_path.iterdir()): # Check if directory is not empty
            # Check if client supports elicitation for confirmation
            try:
                from mcp.types import ClientCapabilities, ElicitationCapability
                elicitation_cap = ClientCapabilities(elicitation=ElicitationCapability())
                supports_elicitation = ctx.session.check_client_capability(elicitation_cap)
                
                if supports_elicitation and not force:
                    # If client supports elicitation, ask for confirmation
                    try:
                        await ctx.elicit(
                            f"Directory '{path}' is not empty. Do you want to delete it and all its contents?",
                            response_type=None
                        )
                        force = True
                    except Exception as e:
                        logger.warning(f"Elicitation failed: {e}")
                        # If elicitation fails, fall back to force parameter
                        pass
            except Exception as e:
                logger.warning(f"Error checking elicitation capability: {e}")
            
            if not force:
                return f"Error: Directory '{path}' is not empty. Use force=True to delete it and its contents."
            
            shutil.rmtree(target_path)
            return f"Successfully deleted directory '{path}' and all its contents."
        else:
            target_path.rmdir()
            return f"Successfully deleted empty directory '{path}'"

    except Exception as e:
        return f"Error deleting directory: {str(e)}"

@mcp.resource("/filesystem/summary/{path}")
async def filesystem_summary(path: str, ctx: Context) -> dict:
    """
    Provides a summary of the filesystem at a given path.
    
    Args:
        path: The root path for the summary.
    """
    target_path = norm_path(path)
    if not await withinAllowed(target_path, ctx):
        return {"error": f"Path '{path}' is not within allowed roots"}

    total_size = 0
    num_files = 0
    num_dirs = 0

    for dirpath, dirnames, filenames in os.walk(target_path):
        num_dirs += len(dirnames)
        num_files += len(filenames)
        for f in filenames:
            fp = os.path.join(dirpath, f)
            # skip if it is symbolic link
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)

    return {
        "path": str(target_path),
        "total_size": format_size(total_size),
        "files": num_files,
        "directories": num_dirs,
    }

@mcp.tool()
async def get_creative_file_description(path: str, ctx: Context) -> str:
    """
    Generates a creative, imaginative description of a file's contents.
    Uses sampling for more creative responses if the feature is supported.
    """
    # First read the file content directly
    try:
        target_path = norm_path(path)
        
        if not await withinAllowed(target_path, ctx):
            return f"Error: Path '{path}' is not within allowed roots"
        
        if not target_path.exists():
            return f"Error: File '{path}' does not exist"
        
        if not target_path.is_file():
            return f"Error: Path '{path}' is not a file"
        
        # Read file contents directly
        content = target_path.read_text(encoding='utf-8')
        content_summary = f"File: {path}\nContent preview: {content[:500]}..." if len(content) > 500 else f"File: {path}\nContent: {content}"
        
    except UnicodeDecodeError:
        return f"Error: File '{path}' contains binary data or unsupported encoding"
    except Exception as e:
        return f"Error reading file: {str(e)}"
    
    # Check if client supports sampling
    try:
        from mcp.types import ClientCapabilities, SamplingCapability
        sampling_cap = ClientCapabilities(sampling=SamplingCapability())
        supports_sampling = ctx.session.check_client_capability(sampling_cap)
        
        if supports_sampling:
            try:
                # Use sampling with higher temperature for more creative responses
                response = await ctx.sample(
                    f"Based on this content, write a short, creative, and imaginative summary of what this file represents. Be poetic or metaphorical:\n\n{content_summary}",
                    temperature=0.9,
                    max_tokens=200
                )
                return str(response)
            except Exception as e:
                logger.warning(f"Sampling failed: {e}")
                # Fallback if sampling fails
                pass
    except Exception as e:
        logger.warning(f"Error checking sampling capability: {e}")
    
    # Default response without sampling
    return f"Analysis of file content:\n\n{content_summary}"

@mcp.tool()
async def analyze_directory_security(path: str, ctx: Context) -> str:
    """
    Provides comprehensive security and content analysis of a directory.
    
    Analyzes file types, potential security risks, content overview,
    and provides intelligent assessment using AI sampling if available.
    
    Args:
        path: Directory path to analyze
        ctx: MCP context for security validation and AI capabilities
    """
    try:
        import hashlib
        import mimetypes
        from datetime import datetime, timedelta
        from collections import defaultdict
        
        target_path = norm_path(path)
        
        if not await withinAllowed(target_path, ctx):
            return f"Error: Path '{path}' is not within allowed roots"
        
        if not target_path.exists():
            return f"Error: Path '{path}' does not exist"
        
        if not target_path.is_dir():
            return f"Error: Path '{path}' is not a directory"
        
        # Enhanced data collection
        file_types = {}
        mime_types = defaultdict(int)
        suspicious_files = []
        executable_files = []
        large_files = []
        hidden_files = []
        duplicate_files = defaultdict(list)  # hash -> [files]
        recent_files = []  # Modified in last 7 days
        old_files = []     # Not modified in last year
        empty_files = []
        
        # Time analysis
        now = datetime.now()
        week_ago = now - timedelta(days=7)
        year_ago = now - timedelta(days=365)
        
        # Directory structure analysis
        depth_stats = defaultdict(int)
        dir_file_counts = defaultdict(int)
        
        # Security patterns
        suspicious_patterns = {
            'password': [],
            'key': [],
            'token': [],
            'secret': [],
            'credential': []
        }
        
        total_size = 0
        total_files = 0
        total_dirs = 0
        sample_files = []
        
        # Known suspicious extensions and patterns
        suspicious_extensions = {'.exe', '.scr', '.bat', '.cmd', '.com', '.pif', '.vbs', '.ps1', '.jar', '.app', '.dmg'}
        executable_extensions = {'.exe', '.msi', '.deb', '.rpm', '.app', '.dmg', '.run', '.sh', '.bat', '.cmd', '.ps1'}
        archive_extensions = {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2'}
        
        logger.info(f"Starting comprehensive analysis of {target_path}")
        
        for root, dirs, files in os.walk(target_path):
            current_depth = len(Path(root).relative_to(target_path).parts)
            depth_stats[current_depth] += 1
            total_dirs += len(dirs)
            dir_file_counts[len(files)] += 1
            
            for file in files:
                file_path = Path(root) / file
                try:
                    file_stat = file_path.stat()
                    file_size = file_stat.st_size
                    total_size += file_size
                    total_files += 1
                    
                    # Basic file analysis
                    ext = file_path.suffix.lower()
                    file_types[ext] = file_types.get(ext, 0) + 1
                    
                    # MIME type analysis
                    mime_type, _ = mimetypes.guess_type(str(file_path))
                    if mime_type:
                        mime_types[mime_type] += 1
                    
                    # Time analysis
                    mod_time = datetime.fromtimestamp(file_stat.st_mtime)
                    if mod_time > week_ago:
                        recent_files.append(f"{file_path.name} ({mod_time.strftime('%Y-%m-%d')})")
                    elif mod_time < year_ago:
                        old_files.append(f"{file_path.name} ({mod_time.strftime('%Y-%m-%d')})")
                    
                    # Size analysis
                    if file_size == 0:
                        empty_files.append(str(file_path))
                    elif file_size > 100 * 1024 * 1024:  # >100MB
                        large_files.append(f"{file_path.name} ({format_size(file_size)})")
                    
                    # Security analysis
                    if ext in suspicious_extensions:
                        suspicious_files.append(str(file_path))
                    
                    if ext in executable_extensions:
                        executable_files.append(str(file_path))
                    
                    if file.startswith('.'):
                        hidden_files.append(str(file_path))
                    
                    # Check for suspicious patterns in filename
                    filename_lower = file.lower()
                    for pattern in suspicious_patterns:
                        if pattern in filename_lower:
                            suspicious_patterns[pattern].append(str(file_path))
                    
                    # Duplicate detection (for files < 50MB to avoid memory issues)
                    if file_size < 50 * 1024 * 1024 and file_size > 0:
                        try:
                            with open(file_path, 'rb') as f:
                                file_hash = hashlib.md5(f.read()).hexdigest()
                                duplicate_files[file_hash].append(str(file_path))
                        except:
                            pass
                    
                    # Content sampling for analysis
                    if len(sample_files) < 15 and ext in {'.txt', '.py', '.js', '.html', '.css', '.md', '.json', '.xml', '.yml', '.yaml', '.log', '.cfg', '.ini'}:
                        try:
                            if file_size < 50000:  # Only smaller files
                                content = file_path.read_text(encoding='utf-8', errors='ignore')[:1000]
                                sample_files.append(f"[{ext}] {file_path.name}: {content[:150]}...")
                        except:
                            pass
                            
                except (OSError, PermissionError, UnicodeDecodeError):
                    continue
        
        # Find actual duplicates (files with same hash but different paths)
        actual_duplicates = {h: files for h, files in duplicate_files.items() if len(files) > 1}
        
        # Generate comprehensive analysis
        analysis_parts = []
        analysis_parts.append(f"📁 COMPREHENSIVE DIRECTORY ANALYSIS: {path}")
        analysis_parts.append(f"📊 Files: {total_files:,} | Directories: {total_dirs:,} | Size: {format_size(total_size)}")
        analysis_parts.append("")
        
        # File types analysis (top 10)
        analysis_parts.append("📋 FILE TYPES (Top 10):")
        sorted_types = sorted(file_types.items(), key=lambda x: x[1], reverse=True)
        for ext, count in sorted_types[:10]:
            ext_display = ext if ext else "(no extension)"
            percentage = (count / total_files) * 100
            analysis_parts.append(f"  {ext_display}: {count:,} ({percentage:.1f}%)")
        
        # MIME types analysis (top 5)
        if mime_types:
            analysis_parts.append("\n🎭 MIME TYPES (Top 5):")
            sorted_mimes = sorted(mime_types.items(), key=lambda x: x[1], reverse=True)
            for mime, count in sorted_mimes[:5]:
                analysis_parts.append(f"  {mime}: {count:,}")
        
        # Time analysis
        analysis_parts.append(f"\n⏰ TIME ANALYSIS:")
        analysis_parts.append(f"Recent files (last 7 days): {len(recent_files)}")
        analysis_parts.append(f"Old files (>1 year): {len(old_files)}")
        
        # Structure analysis
        max_depth = max(depth_stats.keys()) if depth_stats else 0
        analysis_parts.append(f"\n🏗️ STRUCTURE:")
        analysis_parts.append(f"Maximum depth: {max_depth} levels")
        analysis_parts.append(f"Empty files: {len(empty_files)}")
        
        # Duplicates analysis
        if actual_duplicates:
            total_duplicate_files = sum(len(files) for files in actual_duplicates.values())
            duplicate_waste = sum(
                file_types.get(Path(files[0]).suffix.lower(), 0) * len(files) 
                for files in actual_duplicates.values()
            )
            analysis_parts.append(f"🔄 Duplicates: {len(actual_duplicates)} sets, {total_duplicate_files} files")
        
        # Enhanced security assessment
        analysis_parts.append("\n🔒 ENHANCED SECURITY ASSESSMENT:")
        
        security_score = 100
        concerns = []
        
        # Threat scoring
        if suspicious_files:
            threat_score = min(40, len(suspicious_files) * 2)
            security_score -= threat_score
            concerns.append(f"⚠️  {len(suspicious_files)} potentially suspicious files")
            
        if executable_files:
            exec_score = min(25, len(executable_files))
            security_score -= exec_score
            concerns.append(f"🔧 {len(executable_files)} executable files")
            
        if len(hidden_files) > 20:
            security_score -= 20
            concerns.append(f"👁️  Many hidden files ({len(hidden_files)})")
            
        # Pattern-based threats
        pattern_threats = sum(len(files) for files in suspicious_patterns.values())
        if pattern_threats > 0:
            security_score -= min(15, pattern_threats)
            concerns.append(f"🔍 {pattern_threats} files with suspicious naming patterns")
            
        # Size-based concerns
        if total_size > 50 * 1024 * 1024 * 1024:  # >50GB
            concerns.append(f"📦 Very large directory ({format_size(total_size)})")
        
        # Old file concern
        if len(old_files) > total_files * 0.5:
            concerns.append(f"�️  Many old files ({len(old_files)}) - potential cleanup needed")
        
        analysis_parts.append(f"Security Score: {max(0, security_score)}/100")
        
        if concerns:
            analysis_parts.append("Identified Concerns:")
            for concern in concerns:
                analysis_parts.append(f"  • {concern}")
        else:
            analysis_parts.append("✅ No major security concerns detected")
        
        # Detailed findings
        if suspicious_files[:3]:
            analysis_parts.append(f"\n🚨 SUSPICIOUS FILES (showing 3/{len(suspicious_files)}):")
            for file in suspicious_files[:3]:
                analysis_parts.append(f"  • {Path(file).name}")
        
        if any(suspicious_patterns.values()):
            analysis_parts.append("\n� SUSPICIOUS NAMING PATTERNS:")
            for pattern, files in suspicious_patterns.items():
                if files:
                    analysis_parts.append(f"  {pattern.upper()}: {len(files)} files")
        
        if actual_duplicates:
            analysis_parts.append(f"\n🔄 DUPLICATE ANALYSIS (showing 3/{len(actual_duplicates)}):")
            for i, (hash_val, files) in enumerate(list(actual_duplicates.items())[:3]):
                analysis_parts.append(f"  Set {i+1}: {len(files)} identical files")
                for file in files[:2]:  # Show first 2 of each set
                    analysis_parts.append(f"    • {Path(file).name}")
        
        if recent_files[:5]:
            analysis_parts.append(f"\n🆕 RECENT ACTIVITY (showing 5/{len(recent_files)}):")
            for file in recent_files[:5]:
                analysis_parts.append(f"  • {file}")
        
        basic_analysis = "\n".join(analysis_parts)
        
        # Enhanced AI analysis with more context
        try:
            from mcp.types import ClientCapabilities, SamplingCapability
            sampling_cap = ClientCapabilities(sampling=SamplingCapability())
            supports_sampling = ctx.session.check_client_capability(sampling_cap)
            
            if supports_sampling and sample_files:
                analysis_prompt = f"""Analyze this directory comprehensively:

STATISTICS:
- {total_files:,} files, {total_dirs:,} directories, {format_size(total_size)}
- Top types: {', '.join([f"{ext}({count})" for ext, count in sorted_types[:5]])}
- Security score: {max(0, security_score)}/100
- {len(recent_files)} recent files, {len(old_files)} old files
- {len(actual_duplicates)} duplicate sets, {len(empty_files)} empty files

SAMPLE CONTENT:
{chr(10).join(sample_files[:8])}

SECURITY CONCERNS:
{chr(10).join(concerns) if concerns else "None detected"}

SUSPICIOUS PATTERNS:
{chr(10).join([f"{k}: {len(v)}" for k, v in suspicious_patterns.items() if v])}

Provide intelligent analysis covering:
1. Directory purpose/type identification
2. Development/project assessment  
3. Security risk evaluation
4. Cleanup/optimization recommendations
5. Data organization insights
6. Overall risk level (Low/Medium/High/Critical)

Be specific, actionable, under 300 words."""

                try:
                    ai_response = await ctx.sample(
                        analysis_prompt,
                        temperature=0.2,  # Lower temperature for factual analysis
                        max_tokens=400
                    )
                    
                    return f"{basic_analysis}\n\n🤖 AI COMPREHENSIVE ANALYSIS:\n{str(ai_response)}"
                    
                except Exception as e:
                    logger.warning(f"AI analysis failed: {e}")
                    
        except Exception as e:
            logger.warning(f"Error checking sampling capability: {e}")
        
        return basic_analysis
        
    except Exception as e:
        return f"Error analyzing directory: {str(e)}"

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
    
    # Import and register system monitoring tools
    import systemmonitoring
    systemmonitoring._init_systemmonitoring(logger, norm_path, withinAllowed)
    systemmonitoring.register_tools(mcp)

    # Run the server
    mcp.run(transport="sse", host="0.0.0.0", port=8000)

