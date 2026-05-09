import logging

from fastmcp.dependencies import Depends
from fastmcp.server.dependencies import AccessToken, get_access_token

from auth.PolicyManager import policy_manager
from config import settings
from utilities.error_handling import ToolOperationError

module_logger = logging.getLogger("auth_permissions")


async def check_github_account():
    """Pulls user information from context"""
    if not settings.AUTH_ENABLED:
        return None

    try:
        # there are two ways to get access token: from request context (if available)
        # or from get_access_token() for non-request contexts
        token: AccessToken | None = get_access_token()
        if token is None:
            module_logger.debug("No access token found in context")
            return None

        claims = token.claims
        user_claims = claims.get("github_user_data") or {}

        username = claims.get("login") or user_claims.get("login") or user_claims.get("id")
        user_id = user_claims.get("id") or claims.get("sub")

        return {
            "username": str(username) if username is not None else None,
            "user_id": str(user_id) if user_id is not None else None,
            "scopes": token.scopes,
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
            "Error in check_github_account: %s: %s", type(e).__name__, e, exc_info=True
        )
        return None


# def get_github_user_info(ctx: Context, key:str) -> Any:


def get_github_username() -> str | None:
    """
    Extract GitHub username from context.
    Returns None if no authentication or user not found.
    """
    try:
        token: AccessToken | None = get_access_token()
        if token is None:
            module_logger.debug("No access token found in context")
            return None

        claims = token.claims
        user_claims = claims.get("github_user_data") or {}

        username = claims.get("login") or user_claims.get("login") or user_claims.get("id")
        return str(username) if username is not None else None
    except Exception as e:
        module_logger.debug(f"Could not extract GitHub username: {e}")
        return None


def get_github_user_id() -> str | None:
    """
    Extract GitHub user ID from context.
    Returns None if no authentication or user not found.
    """
    try:
        token: AccessToken | None = get_access_token()
        if token is None:
            module_logger.debug("No access token found in context")
            return None

        claims = token.claims
        user_claims = claims.get("github_user_data") or {}

        user_id = user_claims.get("id") or claims.get("sub")

        if user_id:
            return str(user_id)

        return None
    except Exception as e:
        module_logger.debug(f"Could not extract GitHub user ID: {e}")
        return None


def is_authenticated() -> bool:
    """Check if user is authenticated (has valid GitHub session)"""
    if not settings.AUTH_ENABLED:
        return True  # аuth disabled = everyone is "authenticated"

    user_id = get_github_user_id()
    return user_id is not None


def guard(permission: str):

    async def _guard_logic(user_id: str = Depends(get_github_user_id)) -> dict:
        if not settings.AUTH_ENABLED:
            return {}  # no auth = no constraints

        if not user_id:
            raise ToolOperationError(
                "permission_denied",
                "Identity not verified or no user associated with the context.",
                actions=["Authenticate via GitHub and retry the operation."],
            )

        if not policy_manager.check_access(user_id, permission):
            role = policy_manager.get_user_role(user_id)
            raise ToolOperationError(
                "permission_denied",
                f"Your current role is '{role}'. Role '{role}' lacks permission: {permission}.",
                actions=[
                    "Request the required permission from an administrator.",
                    "Ensure your account has the correct role.",
                ],
            )
        return policy_manager.get_constraints(user_id, permission)

    return _guard_logic
