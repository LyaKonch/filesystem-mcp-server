import logging
import secrets
import time
import uuid
from pathlib import Path

from fastmcp import Context, FastMCP
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response

from config import settings
from utilities import dependencies
from utilities.error_handling import tool_error_boundary
from utilities.logging import clear_log_context, set_log_context

module_logger = logging.getLogger(__name__)

# token -> (filename, expires_at)
_download_tokens: dict[str, tuple[Path, float]] = {}


def generate_download_token(file_path: Path, expires_in: int = 300) -> str:
    """Generate a temporary download token.

    Args:
        file_path: File path bound to generated token.
        expires_in: Token lifetime in seconds.

    Returns:
        str: Generated token value.
    """
    token = secrets.token_urlsafe(32)
    expires_at = time.time() + expires_in
    _download_tokens[token] = (file_path, expires_at)
    return token


def is_download_token_valid(token: str) -> Path | None:
    """Validate token and return associated file path.

    Args:
        token: Download token.

    Returns:
        Path | None: Bound file path when valid, otherwise ``None``.
    """
    if token not in _download_tokens:
        return None
    file_path_expected, expires_at = _download_tokens[token]
    if time.time() > expires_at:
        del _download_tokens[token]
        return None
    return file_path_expected


def cleanup_expired_tokens():
    """Remove expired download tokens from memory.

    Returns:
        int: Number of removed tokens.
    """
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
    Prepare a validated file for one-time token-based download.

    Args:
        file_path: Absolute or relative path to file.
        ctx: MCP context.

    Returns:
        str: Download URL with token and trace id.
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
    trace_id = str(uuid.uuid4())
    return (
        f"File {validated_path.name} prepared for download. "
        f"Access it at http://{settings.MCP_HOST}:{settings.MCP_PORT}/download?token={token}&trace_id={trace_id}. "
        "Download link is valud for 5 minutes."
    )


def ft_register_routes(mcp: FastMCP):
    """Register download HTTP route and related MCP tool.

    Args:
        mcp: FastMCP server object.
    """

    def _with_trace(response: Response, trace_id: str) -> Response:
        response.headers["X-Trace-Id"] = trace_id
        return response

    async def download_file(request: Request) -> Response:
        request_id = str(uuid.uuid4())
        trace_id = request.headers.get("X-Trace-Id") or request.query_params.get("trace_id")
        if not trace_id:
            trace_id = request_id

        set_log_context(request_id=request_id, trace_id=trace_id, user_id="-", operation="download")
        file_path: Path | None = None
        try:
            cleanup_expired_tokens()

            token = request.query_params.get("token")

            if token:
                file_path = is_download_token_valid(token)
                if not file_path:
                    return _with_trace(
                        JSONResponse({"error": "Invalid or expired token"}, status_code=403),
                        trace_id,
                    )
            elif settings.AUTH_ENABLED:
                if not hasattr(request, "user") or not request.user.is_authenticated:
                    return _with_trace(
                        JSONResponse({"error": "Authentication required"}, status_code=401),
                        trace_id,
                    )
                return _with_trace(
                    JSONResponse({"error": "Download token is required"}, status_code=400),
                    trace_id,
                )
            else:
                return _with_trace(
                    JSONResponse({"error": "Download token is required"}, status_code=400),
                    trace_id,
                )

            module_logger.info("Received download request for file: %s", file_path.name)

            try:
                # we dont have mcp context on custom route, so here we aren't able to check roots or permissions,
                # but we can check if file is still valid and exists before sending it to user
                # may be a security breach if roots are changed too fast
                checked_path = dependencies.check_path(file_path, check_existence=True)
                if checked_path.is_file():
                    module_logger.info(
                        "File %s is valid and ready for download.", checked_path.name
                    )
                    return _with_trace(
                        FileResponse(
                            checked_path,
                            media_type="application/octet-stream",
                            filename=checked_path.name,
                        ),
                        trace_id,
                    )
                return _with_trace(
                    JSONResponse(
                        {
                            "status": "error",
                            "message": f"File {checked_path.name} is not accessible or does not exist.",
                        },
                        status_code=404,
                    ),
                    trace_id,
                )
            except ValueError as e:
                module_logger.warning("File %s is not valid or accessible: %s", file_path.name, e)
                return _with_trace(
                    JSONResponse(
                        {
                            "status": "error",
                            "message": f"File {file_path.name} is not accessible or does not exist.",
                        }
                    ),
                    trace_id,
                )
        finally:
            clear_log_context()

    mcp.custom_route("/download", methods=["GET"])(download_file)
    mcp.tool("prepare_file_for_download")(
        tool_error_boundary(prepare_file_for_download, module_logger)
    )
