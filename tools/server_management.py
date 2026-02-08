from typing import List
from pathlib import Path
from fastmcp import Context
from utilities import dependencies
from config import settings

async def get_server_status(ctx: Context) -> dict:
    """Get information about server status, client features, and allowed roots."""
    dependencies.logger.info("Checking server status")
    
    features = {
        "elicitation": dependencies.checkElicitationCapability(ctx.session),
        "sampling": dependencies.checkSamplingCapability(ctx.session),
        "roots": dependencies.checkRootsCapability(ctx.session),
    }
    
    client_roots_list = []
    if features["roots"]:
        try:
            roots = await dependencies.fetch_roots_from_client(ctx)
            if roots:
                client_roots_list = [str(r) for r in roots]
        except Exception as e:
            dependencies.logger.warning(f"Error getting client roots: {e}")
            
    return {
        "transport": settings.TRANSPORT,
        "auth_enabled": settings.AUTH_ENABLED,
        "client_features": features,
        "client_roots": client_roots_list,
        "server_roots": [str(path) for path in settings.ALLOWED_ROOTS]
    }

async def list_allowed_roots(ctx: Context) -> str:
    """Get a formatted list of all currently allowed root directories."""
    try:
        combined_roots = await dependencies.get_combined_roots(ctx)
        
        if not combined_roots:
            return "No allowed roots configured."

        lines = ["Allowed Root Directories:"]
        for i, root in enumerate(combined_roots, 1):
            source = "Server" if root in settings.ALLOWED_ROOTS else "Client"
            lines.append(f"{i}. {root} ({source})")
            
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {str(e)}"

async def add_allowed_root(path: str, ctx: Context) -> str:
    """Add a path to the server's allowed roots whitelist at runtime."""
    try:
        path_obj = dependencies.check_path(path, check_existence=True)
        
        if not path_obj.is_dir():
            return f"Error: '{path}' is not a directory"

        if path_obj not in settings.ALLOWED_ROOTS:
            settings.ALLOWED_ROOTS.append(path_obj)
            return f"Successfully added '{path_obj}' to allowed roots."
        
        return f"Path '{path_obj}' is already in allowed roots."
    except Exception as e:
        return f"Error: {str(e)}"

async def update_roots(newroots: List[str]) -> str:
    """Update allowed roots from a list of paths.
    
    Args:
        ctx: List of new root paths
    """
    try:
        new_roots = []
        for p in newroots:
            try:
                path_obj = dependencies.check_path(Path(p),check_existence=True)
                if path_obj.is_dir():
                    new_roots.append(path_obj)
                else:
                    return f"Error: Path '{p}' does not exist or is not a directory"
            except Exception as e:
                return f"Error processing path '{p}': {str(e)}"
        
        if not new_roots:
            return "Error: No valid directories provided"
        
        settings.ALLOWED_ROOTS.clear()
        settings.ALLOWED_ROOTS.extend(new_roots)
        return f"Updated allowed roots to {len(new_roots)} directories"
    
    except Exception as e:
        return f"Error updating roots: {str(e)}"

async def remove_root(root: str) -> str:
    """Remove a single allowed root path."""
    try:
        path_obj = dependencies.check_path(Path(root), check_existence=True)
        if not path_obj.is_dir():
            return f"Error: Path '{root}' is not a directory"

        if path_obj not in settings.ALLOWED_ROOTS:
            return f"Error: Root '{root}' not found in allowed roots"

        settings.ALLOWED_ROOTS.remove(path_obj)
        return f"Removed root '{root}'"
    except (TypeError, ValueError, OSError) as exc:
        return f"Error processing path '{root}': {str(exc)}"
    except Exception as exc:
        return f"Error removing root: {str(exc)}"


def register(mcp):
    mcp.tool(tags=["management"])(get_server_status)
    mcp.tool(tags=["management", "admin"])(add_allowed_root)
    mcp.tool(tags=["management"])(list_allowed_roots)
    mcp.tool(tags=["management", "admin"])(update_roots)
    mcp.tool(tags=["management", "admin"])(remove_root)