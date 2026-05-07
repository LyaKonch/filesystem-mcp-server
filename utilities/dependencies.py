import logging
import os
import re
from pathlib import Path
from typing import Literal, cast
from urllib.parse import unquote, urlparse

import fastmcp
from mcp import ServerSession
from mcp.types import ClientCapabilities, ElicitationCapability, RootsCapability, SamplingCapability

from config import settings
from utilities.error_handling import ToolOperationError

logger = logging.getLogger(__name__)


async def get_combined_roots(context: fastmcp.Context) -> list[Path]:
    result_list: list[Path] = []
    if settings.ALLOWED_ROOTS is not None:
        result_list = [p for p in settings.ALLOWED_ROOTS]
    if checkRootsCapability(context.session):
        clients_roots = await fetch_roots_from_client(context)
        if clients_roots is not None:
            clients_roots_checked = [check_path(p) for p in clients_roots]
            result_list.extend(clients_roots_checked)
    return result_list


# def convert_roots_to_str() -> list[Path]:
#     ROOTS_STR: dict[str, list[Path]] = {
#         "command_line": [],
#         "client_roots": [],
#         "config_file": []
#     }
#     for key, roots_list in ROOTS.items():
#         ROOTS_STR[key] = [str(root) for root in roots_list] if len(roots_list) > 0 else ""
#     return ROOTS_STR


def uri_to_path(uri: str) -> Path:
    """Convert a file:// URI to a Path object."""
    " For example from file://C:\Program Files\ to Path('C:/Program Files')"
    " Path must contain slash at the end and not have any spelling mistakes "
    p = urlparse(uri)
    if p.scheme != "file":
        raise ToolOperationError(
            "validation",
            f"URI must start with file:// but got {p.scheme}://",
            actions=[
                "Use a valid file:// URI.",
                "Format: file:///C:/path/to/file (Windows) or file:///home/user/file (Unix).",
                "Retry with a correct URI.",
            ],
        )

    raw_path = unquote(p.path or "")
    raw_netloc = unquote(p.netloc or "")

    if os.name == "nt":
        if raw_netloc:
            if raw_netloc.lower() == "localhost":
                raw_netloc = ""
            elif len(raw_netloc) == 2 and raw_netloc[1] == ":":
                raw_path = f"{raw_netloc}{raw_path}"
            elif re.match(r"^[A-Za-z]:", raw_netloc):
                raw_path = raw_netloc
            else:
                raise ToolOperationError(
                    "validation",
                    f"Remote file URI host '{raw_netloc}' is not supported. Only localhost and drive letters are allowed.",
                    actions=[
                        "Use a local file path or localhost.",
                        "Retry with a supported URI format.",
                    ],
                )

        if re.match(r"^/[A-Za-z]:", raw_path):
            raw_path = raw_path[1:]

        raw_path = re.sub(r"^([A-Za-z]):(?![\\/])", r"\1:/", raw_path)
    else:
        if raw_netloc and raw_netloc.lower() != "localhost":
            raise ToolOperationError(
                "validation",
                f"Remote file URI host '{raw_netloc}' is not supported. Only localhost is allowed.",
                actions=[
                    "Use a local file path or localhost.",
                    "Retry with a supported URI format.",
                ],
            )

    file = Path(raw_path)
    return check_path(file)


def check_path(value: Path | str, check_existence: bool = True) -> Path:
    try:
        # explicitly converts it to Path
        if isinstance(value, str):
            value = Path(value)

        value = Path(os.path.expanduser(value)).resolve()

        if check_existence and not value.exists():
            raise ToolOperationError(
                "not_found",
                f"Path '{value}' does not exist",
                actions=[
                    "Verify the path is correct.",
                    "Check that the file or directory exists.",
                    "Retry with a valid path.",
                ],
            )

        return value

    except ToolOperationError:
        raise
    except (TypeError, ValueError, OSError) as exc:
        logger.error("Invalid path specified: %s", value, exc_info=exc)
        raise ToolOperationError(
            "validation",
            f"Invalid path specified: {value}",
            actions=[
                "Verify the path syntax.",
                "Ensure the path uses forward slashes or valid backslashes.",
                "Retry with a valid path.",
            ],
        ) from exc


async def validate_path(
    path_str: str,
    ctx: fastmcp.Context,
    must_exist: bool = True,
    expected_type: Literal["file", "dir"] | None = None,
) -> Path:
    """Validate a path string and return a Path object if valid, otherwise raise an error."""
    # a bit strange to set ceck_existance to false, but i want to control exceptions here not within inner function
    path = check_path(path_str, check_existence=False)

    if not await withinAllowed(path, ctx):
        raise ToolOperationError(
            "access_denied",
            f"Access denied: Path '{path}' is not within allowed roots.",
            actions=[
                "Use a path within the allowed root directories.",
                "Contact the administrator to expand allowed roots.",
                "Retry with a valid path.",
            ],
        )

    if must_exist and not path.exists():
        raise ToolOperationError(
            "not_found",
            f"Path '{path}' does not exist",
            actions=[
                "Verify the path is correct.",
                "Check that the file or directory exists.",
                "Retry with a valid path.",
            ],
        )

    if must_exist and expected_type:
        if expected_type == "file" and not path.is_file():
            raise ToolOperationError(
                "validation",
                f"Expected file, but '{path.name}' is a directory",
                actions=[
                    "Verify you provided a file path, not a directory.",
                    "Retry with the correct path.",
                ],
            )

        if expected_type == "dir" and not path.is_dir():
            raise ToolOperationError(
                "validation",
                f"Expected directory, but '{path.name}' is a file",
                actions=[
                    "Verify you provided a directory path, not a file.",
                    "Retry with the correct path.",
                ],
            )

    return path


async def fetch_roots_from_client(context: fastmcp.Context) -> list[Path] | None:
    if checkRootsCapability(context.session):
        logger.info("Listing roots from client")
        roots = None
        try:
            roots = await context.list_roots()
            uris: list[Path] = []
            if roots is not None:
                for root in roots:
                    file_url = uri_to_path(str(root.uri))
                    uris.append(file_url)
                logger.info("Fetched roots from client: %s", uris)
                return uris
            else:
                logger.debug("No roots available from client")
        except ToolOperationError as e:
            logger.error("Error converting root URI from client: %s", e)
            raise
        except Exception as e:
            logger.error("Error fetching roots from client: %s", e)
            raise ToolOperationError(
                "unexpected",
                f"Failed to fetch roots from client: {e}",
                actions=[
                    "Check the client configuration.",
                    "Retry the request.",
                ],
            ) from e
    return None


def checkRootsCapability(session: ServerSession) -> bool:
    caps = ClientCapabilities(roots=RootsCapability())
    return session.check_client_capability(caps)


def checkElicitationCapability(session: ServerSession) -> bool:
    caps = ClientCapabilities(elicitation=ElicitationCapability())
    return session.check_client_capability(caps)


def checkSamplingCapability(session: ServerSession) -> bool:
    caps = ClientCapabilities(sampling=SamplingCapability())
    return session.check_client_capability(caps)


async def request_elicitation_permission(context: fastmcp.Context, reason: str) -> bool | None:
    if not checkElicitationCapability(context.session):
        logger.debug("Client does not support elicitation capability")
        return None

    logger.info("Requesting elicitation permission from client for reason: %s", reason)
    try:
        permission = await context.elicit(reason, bool)  # type: ignore[arg-type]
        logger.info("Elicitation result: %s", permission)
        return cast(bool | None, permission)
    except Exception as e:
        logger.error("Error requesting elicitation permission: %s", e)
        raise ToolOperationError(
            "unexpected",
            f"Failed to request elicitation permission from client: {e}",
            actions=[
                "Check the client connection.",
                "Ensure elicitation capability is enabled.",
                "Retry the request.",
            ],
        ) from e


async def withinAllowed(path: Path, ctx: fastmcp.Context) -> bool:
    """Check if a given path is within allowed scopes of Global allowed directories on server and roots from client."""
    current_scope = await get_combined_roots(ctx)

    return is_path_within_scope(path, current_scope)


def is_path_within_scope(path: Path, scope: list[Path]) -> bool:
    """Check if a given path is within the provided scope."""
    p = check_path(path, check_existence=False)
    for root in scope:
        root = check_path(root, check_existence=True)
        try:
            p.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


## Helper functions------
def format_timestamp(timestamp: float) -> str:
    """Format timestamp to readable string."""
    from datetime import datetime

    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def format_size(size: int | float) -> str:
    """Format file size in human readable format."""
    size_f: float = float(size)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_f < 1024.0:
            return f"{size_f:.1f} {unit}"
        size_f /= 1024.0
    return f"{size_f:.1f} PB"


def should_include_file(file_path: Path, base_path: Path, exclude_patterns: list[str]) -> bool:
    """Check if file should be included based on exclude patterns."""
    import fnmatch

    try:
        # Get relative path for pattern matching
        rel_path = file_path.relative_to(base_path)
        rel_path_str = str(rel_path).replace("\\", "/")

        for pattern in exclude_patterns:
            if fnmatch.fnmatch(rel_path_str, pattern):
                return False
            # Also check just the filename
            if fnmatch.fnmatch(file_path.name, pattern):
                return False
    except Exception:
        pass

    return True
