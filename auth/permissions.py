import inspect
import json
import logging
from collections.abc import Callable
from functools import wraps
from typing import Any

from fastmcp import Context
from fastmcp.server.dependencies import get_access_token
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser

from config import settings

module_logger = logging.getLogger("auth_permissions")


class PermissionLevel:
    """Permission levels for users"""

    GUEST = 0  # No auth, no access
    USER = 1  # Authenticated, read-only access
    ADMIN = 2  # Authenticated admin, full access


def check_github_account(ctx: Context):
    """Pulls user information from context"""
    try:
        user: AuthenticatedUser | None = None
        token: Any | None = None

        # there are two ways to get access token: from request context (if available)
        # or from get_access_token() for non-request contexts
        if not ctx.request_context:
            module_logger.debug("No request_context in context")
            try:
                token = get_access_token()
                module_logger.debug(f"Got token from get_access_token(): {token}")
            except Exception as e:
                module_logger.debug(f"Error getting token: {e}")
                return None
        else:
            module_logger.debug("Has request_context")
            request = ctx.request_context.request
            if request is None:
                module_logger.debug("No request object in request_context")
                return None
            user = request.user
            if user:
                module_logger.debug(f"Got user: {user}")
                token = user.access_token
            else:
                module_logger.debug("No user in request")
                return None

        if not token:
            module_logger.debug("No access_token available")
            return None

        token_json = token.model_dump_json()
        token_payload = json.loads(token_json) if token_json else {}
        claims = token_payload.get("claims", {})
        user_claims = claims.get("github_user_data") or {}

        username = claims.get("login") or user_claims.get("login") or user_claims.get("id")
        user_id = user_claims.get("id") or claims.get("sub")

        return {
            "username": str(username) if username is not None else None,
            "user_id": str(user_id) if user_id is not None else None,
            "is_authenticated": user.is_authenticated if user else True,
            "scopes": token.scopes,
            "expires_at": token.expires_at,
            "client_id": token.client_id,
            "token": token_json,
            "profile": {
                "login": user_claims.get("login"),
                "name": user_claims.get("name"),
                "email": user_claims.get("email") or claims.get("email"),
                "avatar_url": user_claims.get("avatar_url"),
                "html_url": user_claims.get("html_url"),
                "repos_url": user_claims.get("repos_url"),
                "blog": user_claims.get("blog"),
                "company": user_claims.get("company"),
                "location": user_claims.get("location"),
                "created_at": user_claims.get("created_at"),
                "updated_at": user_claims.get("updated_at"),
                "public_repos": user_claims.get("public_repos"),
                "public_gists": user_claims.get("public_gists"),
                "followers": user_claims.get("followers"),
                "following": user_claims.get("following"),
                "two_factor_authentication": user_claims.get("two_factor_authentication"),
                "plan": (user_claims.get("plan") or {}).get("name"),
            },
        }
    except Exception as e:
        module_logger.error(
            f"Error in check_github_account: {type(e).__name__}: {e}", exc_info=True
        )
        return None


def get_github_user_id(ctx: Context) -> str | None:
    """
    Extract GitHub user ID from context.
    Returns None if no authentication or user not found.
    """
    try:
        token_info = check_github_account(ctx)
        if token_info and token_info.get("user_id"):
            return str(token_info["user_id"])

        return None
    except Exception as e:
        module_logger.debug(f"Could not extract GitHub user ID: {e}")
        return None


def is_authenticated(ctx: Context) -> bool:
    """Check if user is authenticated (has valid GitHub session)"""
    if not settings.AUTH_ENABLED:
        return True  # аuth disabled = everyone is "authenticated"

    user_id = get_github_user_id(ctx)
    return user_id is not None


def is_admin(ctx: Context) -> bool:
    """
    Check if the authenticated user is an admin.

    Returns:
        True if user is admin or if auth is disabled
        False if user is not admin or not authenticated
    """
    if not settings.AUTH_ENABLED:
        return True  # auth disabled = everyone is admin

    user_id = get_github_user_id(ctx)

    if not user_id:
        module_logger.debug("No user ID found - not admin")
        return False

    # сheck against admin list
    is_admin_user = user_id in settings.ADMIN_GITHUB_IDS

    if is_admin_user:
        module_logger.debug(f"User {user_id} is admin")
    else:
        module_logger.debug(f"User {user_id} is not in admin list")

    return is_admin_user


def get_permission_level(ctx: Context) -> int:
    """
    Get permission level for current user.

    Returns:
        PermissionLevel.ADMIN (2) - full access
        PermissionLevel.USER (1) - read-only access
        PermissionLevel.GUEST (0) - no access
    """
    if not settings.AUTH_ENABLED:
        return PermissionLevel.ADMIN  # No auth = full access

    if is_admin(ctx):
        return PermissionLevel.ADMIN

    if is_authenticated(ctx):
        return PermissionLevel.USER

    return PermissionLevel.GUEST


def _extract_context_from_args(*args, **kwargs) -> Context | None:
    """Helper to extract Context from function arguments"""
    # Перевіряємо перший позиційний аргумент
    if args and isinstance(args[0], Context):
        return args[0]

    # Перевіряємо kwargs
    if "ctx" in kwargs:
        return kwargs["ctx"]
    if "context" in kwargs:
        return kwargs["context"]

    return None


def require_admin(operation: str = "this operation"):
    """
    Decorator to require admin privileges for a function/method.
    Auto-extracts Context from function arguments (first arg or 'ctx'/'context' kwarg).

    Usage:
        @require_admin("delete file")
        async def delete_file(ctx: Context, path: str):
            ...

    Args:
        operation: Description of the operation (for error message)

    Raises:
        PermissionError: If user is not admin
        ValueError: If Context cannot be extracted from arguments
    """

    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            ctx = _extract_context_from_args(*args, **kwargs)

            if not ctx:
                raise ValueError(f"Could not extract Context from {func.__name__} arguments")

            if not is_admin(ctx):
                user_id = get_github_user_id(ctx) or "anonymous"
                error_msg = f"Admin privileges required for {operation}. User: {user_id}"
                module_logger.warning(f"🚫 Access denied: {error_msg}")
                raise PermissionError(error_msg)

            user_id = get_github_user_id(ctx)
            module_logger.info(f"✅ Admin operation authorized: {operation} by {user_id}")

            return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            ctx = _extract_context_from_args(*args, **kwargs)

            if not ctx:
                raise ValueError(f"Could not extract Context from {func.__name__} arguments")

            if not is_admin(ctx):
                user_id = get_github_user_id(ctx) or "anonymous"
                error_msg = f"Admin privileges required for {operation}. User: {user_id}"
                module_logger.warning(f"🚫 Access denied: {error_msg}")
                raise PermissionError(error_msg)

            user_id = get_github_user_id(ctx)
            module_logger.info(f"✅ Admin operation authorized: {operation} by {user_id}")

            return func(*args, **kwargs)

        # server have sync and async tools, so it should be checked to return proper wrapper
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def require_auth(operation: str = "this operation"):
    """
    Decorator to require authentication for a function/method.
    Auto-extracts Context from function arguments (first arg or 'ctx'/'context' kwarg).

    Usage:
        @require_auth("write file")
        async def write_file(ctx: Context, path: str, content: str):
            ...

    Args:
        operation: Description of the operation (for error message)

    Raises:
        PermissionError: If user is not authenticated
        ValueError: If Context cannot be extracted from arguments
    """

    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            ctx = _extract_context_from_args(*args, **kwargs)

            if not ctx:
                raise ValueError(f"Could not extract Context from {func.__name__} arguments")

            # Перевірка автентифікації
            if not is_authenticated(ctx):
                error_msg = f"Authentication required for {operation}"
                module_logger.warning(f"🚫 Access denied: {error_msg}")
                raise PermissionError(error_msg)

            user_id = get_github_user_id(ctx)
            module_logger.debug(f"✅ Operation authorized: {operation} by {user_id}")

            return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            ctx = _extract_context_from_args(*args, **kwargs)

            if not ctx:
                raise ValueError(f"Could not extract Context from {func.__name__} arguments")

            # Перевірка автентифікації
            if not is_authenticated(ctx):
                error_msg = f"Authentication required for {operation}"
                module_logger.warning(f"🚫 Access denied: {error_msg}")
                raise PermissionError(error_msg)

            user_id = get_github_user_id(ctx)
            module_logger.debug(f"✅ Operation authorized: {operation} by {user_id}")

            return func(*args, **kwargs)

        # Визначаємо чи функція асинхронна
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# should be expanded and elaborated
# def can_access_tool(ctx: Context, tool_tags: list[str]) -> bool:
#
#     if not settings.AUTH_ENABLED:
#         return True  # Auth disabled = all tools accessible

#     permission_level = get_permission_level(ctx)

#     # guest - no access
#     if permission_level == PermissionLevel.GUEST:
#         return False

#     # check for admin-only tags
#     admin_tags = {'admin', 'dangerous'}
#     if any(tag in admin_tags for tag in tool_tags):
#         return permission_level == PermissionLevel.ADMIN

#     # Check for write operations (requires at least USER level)
#     if 'write' in tool_tags:
#         return permission_level >= PermissionLevel.USER

#     # Read-only operations - accessible to authenticated users
#     return permission_level >= PermissionLevel.USER


def log_user_connection(ctx: Context, event: str = "connected"):
    """
    Log user connection/disconnection events.

    Args:
        ctx: FastMCP context
        event: Event type (connected, disconnected, etc.)
    """
    try:
        user_id = get_github_user_id(ctx) or "anonymous"
        permission_level = get_permission_level(ctx)

        level_name = {
            PermissionLevel.GUEST: "GUEST",
            PermissionLevel.USER: "USER",
            PermissionLevel.ADMIN: "ADMIN",
        }.get(permission_level, "UNKNOWN")

        module_logger.info(f"👤 User {event}: {user_id} (Level: {level_name})")

        # Additional metadata logging
        if hasattr(ctx, "session"):
            session_info = {
                "user_id": user_id,
                "permission_level": level_name,
                "event": event,
                "auth_enabled": settings.AUTH_ENABLED,
            }
            module_logger.debug(f"Session info: {session_info}")

    except Exception as e:
        module_logger.error(f"Error logging user connection: {e}")


def get_user_info(ctx: Context) -> dict:
    """
    Get formatted user information for logging/debugging.

    Returns:
        Dictionary with user information
    """
    user_id = get_github_user_id(ctx)
    permission_level = get_permission_level(ctx)

    level_name = {
        PermissionLevel.GUEST: "guest",
        PermissionLevel.USER: "user",
        PermissionLevel.ADMIN: "admin",
    }.get(permission_level, "unknown")

    return {
        "user_id": user_id or "anonymous",
        "authenticated": is_authenticated(ctx),
        "is_admin": is_admin(ctx),
        "permission_level": level_name,
        "auth_enabled": settings.AUTH_ENABLED,
    }
