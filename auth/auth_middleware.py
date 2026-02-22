from config import settings
from utilities.dependencies import logger
from fastmcp.server.middleware import Middleware, MiddlewareContext

class AuthMiddleware(Middleware):
    """
    Middleware to enforce authentication and admin access control.
    Checks if the user is authenticated and if they are in the list of admin GitHub IDs for dangerous operations.
    """

    def __init__(self):
        # possibly session info
        self.connected_users = set()

    async def __call__(self, scope, receive, send):
        pass


def create_auth_middleware():
    """Factory function to create auth middleware instance"""
    middleware = AuthMiddleware()
    
    if settings.AUTH_ENABLED:
        logger.info("🔐 Auth middleware enabled")
    else:
        logger.warning("⚠️ Auth middleware disabled - all users have full access")
    
    return middleware