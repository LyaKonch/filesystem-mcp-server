from fastmcp import FastMCP,Context
from starlette.requests import Request
from starlette.responses import Response, JSONResponse, FileResponse
from config import settings
from utilities import dependencies
from pathlib import Path
from auth.permissions import require_auth
import secrets
import time

 # token -> (filename, expires_at)
_download_tokens: dict[str, tuple[Path,float]] = {}

def generate_download_token(file_path: Path, expires_in: int = 300) -> str:
    """Generate temporary download token (expires in 5 minutes by default)"""
    token = secrets.token_urlsafe(32)
    expires_at = time.time() + expires_in
    _download_tokens[token] = (file_path, expires_at)
    return token

def is_download_token_valid(token: str) -> Path:
    """Verify download token is valid and not expired"""
    if token not in _download_tokens:
        return None
    file_path_expected, expires_at = _download_tokens[token]
    if time.time() > expires_at:
        del _download_tokens[token]
        return None
    return file_path_expected

def cleanup_expired_tokens():
    """Remove all expired tokens from memory"""
    current_time = time.time()
    expired = [token for token, (_, expires_at) in _download_tokens.items() if current_time > expires_at]
    for token in expired:
        del _download_tokens[token]
    return len(expired)

#@require_auth(operation="prepare_file_for_download")
async def prepare_file_for_download(file_path: str, ctx: Context) -> Path:
    '''
    Prepares a file for download by copying it to the server's designated download directory.
    Validates the file path against allowed roots and checks for existence before copying.
    User can then access the file via the /files/{filename} endpoint.
    '''
    try:
        file_path: Path = await dependencies.validate_path(file_path, ctx, must_exist=True, expected_type='file')
    except ValueError as e:
        dependencies.logger.error(f"File {file_path} is not valid or accessible or not within allowed roots: {e}")
        raise

    token = generate_download_token(file_path)
    return f"File {file_path.name} prepared for download. Access it at http://{settings.MCP_HOST}:{settings.MCP_PORT}/download?token={token}. Download link is valud for 5 minutes."

def ft_register_routes(mcp: FastMCP):

    async def download_file(request: Request) -> Response:
        
        cleanup_expired_tokens()

        token = request.query_params.get("token")

        if token:
            file_path = is_download_token_valid(token)
            if not file_path:
                return JSONResponse({"error": "Invalid or expired token"}, status_code=403)
        elif settings.AUTH_ENABLED:
            if not hasattr(request, 'user') or not request.user.is_authenticated:
                return JSONResponse({"error": "Authentication required"}, status_code=401)
        
        dependencies.logger.info(f"Received download request for file: {file_path.name}")
        
        try:
            # we dont have mcp context on custom route, so here we aren't able to check roots or permissions, 
            # but we can check if file is still valid and exists before sending it to user
            # may be a security breach if roots are changed too fast
            file_path: Path = dependencies.check_path(file_path, check_existence=True)
            if file_path.is_file():
                dependencies.logger.info(f"File {file_path.name} is valid and ready for download.")
                return FileResponse(file_path, media_type='application/octet-stream', filename=file_path.name)
        except ValueError as e:
            dependencies.logger.warning(f"File {file_path.name} is not valid or accessible: {e}")
            return JSONResponse({"status": "error", "message": f"File {file_path.name} is not accessible or does not exist."})
        
   
    mcp.custom_route("/download", methods=["GET"])(download_file)
    mcp.tool("prepare_file_for_download")(prepare_file_for_download)
