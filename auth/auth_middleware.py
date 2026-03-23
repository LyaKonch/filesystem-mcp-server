import logging
import uuid
from collections.abc import Mapping

from fastmcp import Context
from fastmcp.server.middleware import Middleware, MiddlewareContext

from auth.permissions import get_github_user_id
from config import settings
from utilities.logging import clear_log_context, set_log_context

module_logger = logging.getLogger("auth_middleware")


class AuthMiddleware(Middleware):
    """
    Middleware that applies authentication and tool visibility checks.

    The middleware also injects request-scoped logging context.
    """

    def __init__(self):
        # possibly session info
        self.connected_users = set()

    @staticmethod
    def _extract_operation(context: MiddlewareContext) -> str:
        op = context.method or "unknown"
        message = getattr(context, "message", None)

        if isinstance(message, Mapping):
            params = message.get("params")
            if isinstance(params, Mapping):
                tool_name = params.get("name")
                if isinstance(tool_name, str) and tool_name:
                    return tool_name
            tool_name = message.get("name")
            if isinstance(tool_name, str) and tool_name:
                return tool_name

        if message is not None and hasattr(message, "name"):
            maybe_name = message.name
            if isinstance(maybe_name, str) and maybe_name:
                return maybe_name

        return op

    @staticmethod
    def _extract_user_id(ctx: Context | None) -> str:
        if not settings.AUTH_ENABLED:
            return "-"
        if not ctx:
            return "-"
        user_id = get_github_user_id(ctx)
        return user_id if user_id else "-"

    @staticmethod
    def _extract_trace_id(context: MiddlewareContext, request_id: str) -> str:
        message = getattr(context, "message", None)
        if isinstance(message, Mapping):
            direct = message.get("trace_id")
            if isinstance(direct, str) and direct:
                return direct

            params = message.get("params")
            if isinstance(params, Mapping):
                param_trace = params.get("trace_id")
                if isinstance(param_trace, str) and param_trace:
                    return param_trace

                meta = params.get("meta")
                if isinstance(meta, Mapping):
                    meta_trace = meta.get("trace_id")
                    if isinstance(meta_trace, str) and meta_trace:
                        return meta_trace

        return request_id

    # this will be a dispatch method
    async def __call__(self, context: MiddlewareContext, call_next):
        request_id = str(uuid.uuid4())
        fastmcp_ctx: Context | None = context.fastmcp_context
        operation = self._extract_operation(context)
        trace_id = self._extract_trace_id(context, request_id)
        user_id = self._extract_user_id(fastmcp_ctx)

        set_log_context(
            request_id=request_id,
            trace_id=trace_id,
            user_id=user_id,
            operation=operation,
        )
        module_logger.debug("🔐 AuthMiddleware: Processing method %s", context.method)

        try:
            # if auth is disabled, allow everything
            if not settings.AUTH_ENABLED:
                return await call_next(context)

            match context.method:
                case "tools/list":
                    return await self._filter_tools(context, call_next, fastmcp_ctx)
                case "tools/call":
                    return await self._check_auth_for_tool_call(context, call_next, fastmcp_ctx)

            return await call_next(context)
        finally:
            clear_log_context()

    async def _check_auth_for_tool_call(
        self, context: MiddlewareContext, call_next, ctx: Context | None
    ):
        """Check authentication before executing a tool call.

        Args:
            context: Middleware request context.
            call_next: Next middleware handler.
            ctx: FastMCP context.

        Returns:
            Any: Result from downstream middleware/tool handler.
        """

        if not ctx:
            module_logger.warning("⚠️ No context available for authentication check")
            raise PermissionError("Authentication required")

        user_id = get_github_user_id(ctx)

        if not user_id:
            tool_name = context.method
            module_logger.warning(f"🚫 Unauthenticated user attempted to call tool: {tool_name}")
            raise PermissionError("Authentication required to call tools")

        module_logger.debug(f"✅ User {user_id} authenticated for tool call")
        return await call_next(context)

    async def _filter_tools(self, context: MiddlewareContext, call_next, ctx: Context | None):
        """Filter visible tools list based on current auth mode.

        Args:
            context: Middleware request context.
            call_next: Next middleware handler.
            ctx: FastMCP context.

        Returns:
            list: Filtered tool definitions.
        """
        result = await call_next(context)

        if not settings.AUTH_ENABLED:
            return result

        if not ctx:
            module_logger.warning("⚠️ No context available for tool filtering")
            return result

        result_list = []
        for tool in result:
            if "admin" not in tool.tags:
                result_list.append(tool)

        # Update the result with filtered tools
        result = result_list
        return result


def create_auth_middleware():
    """Create and initialize ``AuthMiddleware`` instance.

    Returns:
        AuthMiddleware: Configured middleware object.
    """
    middleware = AuthMiddleware()

    if settings.AUTH_ENABLED:
        module_logger.info("🔐 Auth middleware enabled")
    else:
        module_logger.warning("⚠️ Auth middleware disabled - all users have full access")

    return middleware
