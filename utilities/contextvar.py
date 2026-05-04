from contextvars import ContextVar

from fastmcp import Context

current_mcp_ctx: ContextVar[Context | None] = ContextVar("current_mcp_ctx", default=None)
