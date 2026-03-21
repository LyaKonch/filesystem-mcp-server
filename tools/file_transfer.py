import logging
import secrets
import time
from pathlib import Path

from fastmcp import Context, FastMCP
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response

from config import settings
from utilities import dependencies
from utilities.error_handling import tool_error_boundary

module_logger = logging.getLogger(__name__)

# token -> (filename, expires_at)
_download_tokens: dict[str, tuple[Path, float]] = {}


def generate_download_token(file_path: Path, expires_in: int = 300) -> str:
    """Generate temporary download token (expires in 5 minutes by default)"""
    token = secrets.token_urlsafe(32)
    expires_at = time.time() + expires_in
    _download_tokens[token] = (file_path, expires_at)
    return token


def is_download_token_valid(token: str) -> Path | None:
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
    expired = [
        token for token, (_, expires_at) in _download_tokens.items() if current_time > expires_at
    ]
    for token in expired:
        del _download_tokens[token]
    return len(expired)


# @require_auth(operation="prepare_file_for_download")
async def prepare_file_for_download(file_path: str, ctx: Context) -> str:
    """
    Prepares a file for download by copying it to the server's designated download directory.
    Validates the file path against allowed roots and checks for existence before copying.
    User can then access the file via the /files/{filename} endpoint.
    """
    try:
        validated_path = await dependencies.validate_path(
            file_path, ctx, must_exist=True, expected_type="file"
        )
    except ValueError as e:
        module_logger.error(
            f"File {file_path} is not valid or accessible or not within allowed roots: {e}"
        )
        raise

    token = generate_download_token(validated_path)
    return f"File {validated_path.name} prepared for download. Access it at http://{settings.MCP_HOST}:{settings.MCP_PORT}/download?token={token}. Download link is valud for 5 minutes."


def ft_register_routes(mcp: FastMCP):

    async def download_file(request: Request) -> Response:
        file_path: Path | None = None

        cleanup_expired_tokens()

        token = request.query_params.get("token")

        if token:
            file_path = is_download_token_valid(token)
            if not file_path:
                return JSONResponse({"error": "Invalid or expired token"}, status_code=403)
        elif settings.AUTH_ENABLED:
            if not hasattr(request, "user") or not request.user.is_authenticated:
                return JSONResponse({"error": "Authentication required"}, status_code=401)
            return JSONResponse({"error": "Download token is required"}, status_code=400)
        else:
            return JSONResponse({"error": "Download token is required"}, status_code=400)

        module_logger.info("Received download request for file: %s", file_path.name)

        try:
            # we dont have mcp context on custom route, so here we aren't able to check roots or permissions,
            # but we can check if file is still valid and exists before sending it to user
            # may be a security breach if roots are changed too fast
            checked_path = dependencies.check_path(file_path, check_existence=True)
            if checked_path.is_file():
                module_logger.info("File %s is valid and ready for download.", checked_path.name)
                return FileResponse(
                    checked_path,
                    media_type="application/octet-stream",
                    filename=checked_path.name,
                )
            return JSONResponse(
                {
                    "status": "error",
                    "message": f"File {checked_path.name} is not accessible or does not exist.",
                },
                status_code=404,
            )
        except ValueError as e:
            module_logger.warning("File %s is not valid or accessible: %s", file_path.name, e)
            return JSONResponse(
                {
                    "status": "error",
                    "message": f"File {file_path.name} is not accessible or does not exist.",
                }
            )

    mcp.custom_route("/download", methods=["GET"])(download_file)
    mcp.tool("prepare_file_for_download")(
        tool_error_boundary(prepare_file_for_download, module_logger)
    )
