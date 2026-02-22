import logging
from config import settings
from utilities.dependencies import logger
from fastmcp import Context
from fastmcp.server.middleware import Middleware, MiddlewareContext
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from fastmcp.server.dependencies import get_access_token

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
        match context.method:
            case "tools/list":
                return await self._filter_tools(context, call_next, context.fastmcp_context)
            
        return await call_next(context)

    async def _filter_tools(self, context: MiddlewareContext, call_next, ctx: Context):
        result = await call_next(context)
        
        if not settings.AUTH_ENABLED:
            return result

        if not ctx:
            module_logger.warning("⚠️ No context available for tool filtering")
            return result
        
        user_info = self.check_github_account(ctx)
        module_logger.info(f"User info: {user_info}")
        
        if not user_info:
            module_logger.warning("🚫 User is not authenticated")
            raise ValueError("User is not authenticated")
        
        module_logger.info(f"✅ User authenticated: {user_info.get('username', 'Unknown')}")
        return result
    
    def check_github_account(self, ctx: Context):
        """Витягує юзера з контексту"""
        try:
            user: AuthenticatedUser = None
            token: AccessToken = None
            
            # there are two ways to get acess token: from request context (if available) 
            # or from get_access_token() for non-request contexts
            # second one is more reliable, thus it serves here as fallback  
            if not ctx.request_context:
                module_logger.debug("No request_context in context")
                try:
                    token: AccessToken = get_access_token()
                    module_logger.debug(f"Got token from get_access_token(): {token}")
                    if token:
                        return {
                            "token": token.model_dump_json(),
                            "scopes": token.scopes,
                            "client_id": token.client_id,
                        }
                except Exception as e:
                    module_logger.debug(f"Error getting token: {e}")
                    return None
            else:
                module_logger.debug("Has request_context")
                request = ctx.request_context.request
                user: AuthenticatedUser = request.user
                
                if user:
                    module_logger.debug(f"Got user: {user}")
                    token: AccessToken = user.access_token
                    
                    if token:
                        return {
                            "username": user.username,
                            "is_authenticated": user.is_authenticated,
                            "scopes": token.scopes ,
                            "expires_at": token.expires_at ,
                            "client_id": token.client_id ,
                            "token": token.model_dump_json()
                        }
                    else:
                        module_logger.debug("No access_token in user")
                        return None
                else:
                    module_logger.debug("No user in request")
                    return None
                
        except Exception as e:
            module_logger.error(f"Error in check_github_account: {type(e).__name__}: {e}", exc_info=True)
            return None

def create_auth_middleware():
    """Factory function to create auth middleware instance"""
    middleware = AuthMiddleware()
    
    if settings.AUTH_ENABLED:
        module_logger.info("🔐 Auth middleware enabled")
    else:
        module_logger.warning("⚠️ Auth middleware disabled - all users have full access")
    
    return middleware