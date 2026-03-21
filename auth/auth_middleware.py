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
    Middleware to enforce authentication and admin access control.
    Checks if the user is authenticated and if they are in the list of admin GitHub IDs for dangerous operations.
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

    # this will be a dispatch method
    async def __call__(self, context: MiddlewareContext, call_next):
        request_id = str(uuid.uuid4())
        fastmcp_ctx: Context | None = context.fastmcp_context
        operation = self._extract_operation(context)
        user_id = self._extract_user_id(fastmcp_ctx)

        set_log_context(request_id=request_id, user_id=user_id, operation=operation)
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
        """Check authentication before executing any tool"""

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
        """Filter tools list based on user permissions (optional future feature)"""
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
    """Factory function to create auth middleware instance"""
    middleware = AuthMiddleware()

    if settings.AUTH_ENABLED:
        module_logger.info("🔐 Auth middleware enabled")
    else:
        module_logger.warning("⚠️ Auth middleware disabled - all users have full access")

    return middleware
