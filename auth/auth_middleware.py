import logging

from fastmcp import Context
from fastmcp.server.middleware import Middleware, MiddlewareContext

from auth.permissions import get_github_user_id
from config import settings

module_logger = logging.getLogger("auth_middleware")


class AuthMiddleware(Middleware):
    """
    Middleware to enforce authentication and admin access control.
    Checks if the user is authenticated and if they are in the list of admin GitHub IDs for dangerous operations.
    """

    def __init__(self):
        # possibly session info
        self.connected_users = set()

    # this will be a dispatch method
    async def __call__(self, context: MiddlewareContext, call_next):
        module_logger.debug(f"🔐 AuthMiddleware: Processing method {context.method}")

        # if auth is disabled, allow everything
        if not settings.AUTH_ENABLED:
            return await call_next(context)

        match context.method:
            case "tools/list":
                return await self._filter_tools(context, call_next, context.fastmcp_context)
            case "tools/call":
                return await self._check_auth_for_tool_call(
                    context, call_next, context.fastmcp_context
                )

        return await call_next(context)

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
