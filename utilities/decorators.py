import logging


def export_tool(name=None, description=None, logger=None, tags=None):
    """Decorator to mark a function as an MCP tool with optional metadata."""

    def decorator(func):
        func._is_mcp_tool = True  # Ставимо "якорець"
        func._tool_name = name or func.__name__
        func._tool_desc = description or func.__doc__
        func._tool_logger = logger or logging.getLogger(func.__module__)
        func._tool_tags = set(tags) if tags else set()
        return func

    return decorator


def export_custom_route(custom_route=None, methods=None, logger=None):
    """Decorator to mark a function as an MCP tool with optional metadata."""

    def decorator(func):
        func._custom_route = custom_route
        func._methods = methods
        func._tool_logger = logger or logging.getLogger(func.__module__)
        return func

    return decorator
