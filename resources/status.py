from utilities import dependencies
from fastmcp import Context

#@mcp.resource("/filesystem/summary/{path}")
async def get_client_features(ctx: Context) -> dict:
    """Get information about which features the client supports."""
    dependencies.logger.info("Checking client capabilities")
    
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
        dependencies.logger.warning(f"Error checking elicitation capability: {e}")
        features["elicitation"] = False
    
    try:
        from mcp.types import ClientCapabilities, SamplingCapability
        sampling_cap = ClientCapabilities(sampling=SamplingCapability())
        features["sampling"] = ctx.session.check_client_capability(sampling_cap)
    except Exception as e:
        dependencies.logger.warning(f"Error checking sampling capability: {e}")
        features["sampling"] = False
    
    try:
        from mcp.types import ClientCapabilities, RootsCapability
        roots_cap = ClientCapabilities(roots=RootsCapability())
        features["roots"] = ctx.session.check_client_capability(roots_cap)
    except Exception as e:
        dependencies.logger.warning(f"Error checking roots capability: {e}")
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
                        root_path = dependencies.uri_to_path(uri)
                        client_roots_list.append(str(root_path))
                        dependencies.logger.info(f"Found client root: {root_path}")
        except Exception as e:
            dependencies.logger.warning(f"Error getting client roots: {e}")
            
    return {
        "features": features,
        "client_roots": client_roots_list,
        "command_line_roots": [str(path) for path in CMD_LINE_ROOTS]
    }