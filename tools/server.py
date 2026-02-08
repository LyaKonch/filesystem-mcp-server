import sys
from typing import List
from pathlib import Path
from fastmcp import Context
from utilities import dependencies
from config import settings


async def get_allowed_roots(ctx: Context) -> str:
    """Get the list of currently allowed root directories.
    
    Returns:
        List of allowed root directories
    """
    try:
        supports_roots = dependencies.checkRootsCapability(ctx.session)
        current_roots = dependencies.GLOBAL_ROOTS
        if supports_roots:
            current_roots = await dependencies.get_combined_roots(ctx)
            if not current_roots:
                return "No allowed clients roots configured"
        
        roots_info = [f"Client supports roots: {supports_roots}"]
        roots_info.append(f"Server command line args: {' '.join(sys.argv[1:]) if len(sys.argv) > 1 else 'none'}")
        roots_info.append("")
        
        for i, root in enumerate(current_roots, 1):
            roots_info.append(f"{i}. {root}")
        
        return "Allowed root directories:\n" + "\n".join(roots_info)
    
    except Exception as e:
        return f"Error getting allowed roots: {str(e)}"


async def update_roots(newroots: List[str]) -> str:
    """Update allowed roots from a list of paths.
    
    Args:
        ctx: List of new root paths
    """
    try:
        new_roots = []
        for p in newroots:
            try:
                path_obj = dependencies.check_path(Path(p))
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


async def add_roots(newroots: List[str]) -> str:
    """Add allowed roots from a list of paths.

    Args:
        ctx: List of new root paths
    """
    try:
        added_roots = []
        for p in newroots:
            try:
                path_obj = dependencies.check_path(Path(p))
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
