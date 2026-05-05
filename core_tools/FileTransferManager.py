import logging
import secrets
import time
import uuid
from pathlib import Path

from fastmcp import Context
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response

from config import settings
from utilities import dependencies
from utilities.decorators import export_custom_route, export_tool
from utilities.error_handling import ToolOperationError
from utilities.logging import clear_log_context, set_log_context


class FileTransferManager:
    def __init__(self):
        # token -> (filename, expires_at)
        self._download_tokens: dict[str, tuple[Path, float]] = {}
        self.module_logger = logging.getLogger(__name__)

    # def upload_file(self, file_path, destination):
    #    pass

    # def download_file(self, file_path, destination):
    #    pass

    def generate_download_token(self, file_path: Path, expires_in: int = 300) -> str:
        """Generate temporary download token (expires in 5 minutes by default)"""
        token = secrets.token_urlsafe(32)
        expires_at = time.time() + expires_in
        self._download_tokens[token] = (file_path, expires_at)
        return token

    def is_download_token_valid(self, token: str) -> Path | None:
        """Verify download token is valid and not expired"""
        if token not in self._download_tokens:
            return None
        file_path_expected, expires_at = self._download_tokens[token]
        if time.time() > expires_at:
            del self._download_tokens[token]
            return None
        return file_path_expected

    def cleanup_expired_tokens(self):
        """Remove all expired tokens from memory"""
        current_time = time.time()
        expired = [
            token
            for token, (_, expires_at) in self._download_tokens.items()
            if current_time > expires_at
        ]
        for token in expired:
            del self._download_tokens[token]
        return len(expired)

    # @require_auth(operation="prepare_file_for_download")
    @export_tool(name="prepare_file_for_download", logger=logging.getLogger(__name__))
    async def prepare_file_for_download(self, file_path: str, ctx: Context) -> str:
        """Prepare a secure temporary download link for a file.

        Validates path and permissions, then returns a short-lived token URL
        that can be used by clients to download the file safely.
        """
        try:
            validated_path = await dependencies.validate_path(
                file_path, ctx, must_exist=True, expected_type="file"
            )
        except ToolOperationError:
            raise
        except Exception as e:
            self.module_logger.error(
                f"File {file_path} is not valid or accessible or not within allowed roots: {e}"
            )
            raise ToolOperationError(
                "operation_failed",
                f"Failed to prepare file '{file_path}' for download: {e}",
                actions=[
                    "Verify the file exists and is accessible.",
                    "Check file permissions and allowed roots.",
                    "Retry the operation.",
                ],
            ) from e

        token = self.generate_download_token(validated_path)
        trace_id = str(uuid.uuid4())
        return (
            f"File {validated_path.name} prepared for download. "
            f"Access it at http://{settings.MCP_HOST}:{settings.MCP_PORT}/download?token={token}&trace_id={trace_id}. "
            "Download link is valid for 5 minutes."
        )

    def _with_trace(self, response: Response, trace_id: str) -> Response:
        response.headers["X-Trace-Id"] = trace_id
        return response

    @export_custom_route(
        custom_route="/download", methods=["GET"], logger=logging.getLogger(__name__)
    )
    async def download_file(self, request: Request) -> Response:
        request_id = str(uuid.uuid4())
        trace_id = request.headers.get("X-Trace-Id") or request.query_params.get("trace_id")
        if not trace_id:
            trace_id = request_id

        set_log_context(request_id=request_id, trace_id=trace_id, user_id="-", operation="download")
        file_path: Path | None = None
        try:
            self.cleanup_expired_tokens()

            token = request.query_params.get("token")

            if token:
                file_path = self.is_download_token_valid(token)
                if not file_path:
                    return self._with_trace(
                        JSONResponse({"error": "Invalid or expired token"}, status_code=403),
                        trace_id,
                    )
            elif settings.AUTH_ENABLED:
                if not hasattr(request, "user") or not request.user.is_authenticated:
                    return self._with_trace(
                        JSONResponse({"error": "Authentication required"}, status_code=401),
                        trace_id,
                    )
                return self._with_trace(
                    JSONResponse({"error": "Download token is required"}, status_code=400),
                    trace_id,
                )
            else:
                return self._with_trace(
                    JSONResponse({"error": "Download token is required"}, status_code=400),
                    trace_id,
                )

            self.module_logger.info("Received download request for file: %s", file_path.name)

            try:
                # we dont have mcp context on custom route, so here we aren't able to check roots or permissions,
                # but we can check if file is still valid and exists before sending it to user
                # may be a security breach if roots are changed too fast
                checked_path = dependencies.check_path(file_path, check_existence=True)
                if checked_path.is_file():
                    self.module_logger.info(
                        "File %s is valid and ready for download.", checked_path.name
                    )
                    return self._with_trace(
                        FileResponse(
                            checked_path,
                            media_type="application/octet-stream",
                            filename=checked_path.name,
                        ),
                        trace_id,
                    )
                return self._with_trace(
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
                self.module_logger.warning(
                    "File %s is not valid or accessible: %s", file_path.name, e
                )
                return self._with_trace(
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
