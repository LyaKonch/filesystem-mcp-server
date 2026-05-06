import logging
from pathlib import Path

from fastmcp import Context

from auth.permissions import guard
from config import settings
from utilities import dependencies
from utilities import logging as log_context
from utilities.decorators import export_tool
from utilities.error_handling import ToolOperationError
from utilities.error_reports import save_error_report


class ServerManager:
    def __init__(self):
        self.module_logger = logging.getLogger(__name__)

    @guard("server.get_server_status")
    @export_tool(
        name="get_server_status",
        logger=logging.getLogger(__name__),
        tags=["server.get_server_status"],
    )
    async def get_server_status(self, ctx: Context, constraints: dict | None = None) -> dict:
        """Get information about server status, client features, and allowed roots."""
        self.module_logger.info("Checking server status")

        features = {
            "elicitation": dependencies.checkElicitationCapability(ctx.session),
            "sampling": dependencies.checkSamplingCapability(ctx.session),
            "roots": dependencies.checkRootsCapability(ctx.session),
        }

        client_roots_list = []
        if features["roots"]:
            try:
                roots = await dependencies.fetch_roots_from_client(ctx)
                if roots:
                    client_roots_list = [str(r) for r in roots]
            except Exception as e:
                self.module_logger.warning("Error getting client roots: %s", e)

        return {
            "transport": settings.TRANSPORT,
            "auth_enabled": settings.AUTH_ENABLED,
            "client_features": features,
            "client_roots": client_roots_list,
            "server_roots": [str(path) for path in settings.ALLOWED_ROOTS],
        }

    @guard("server.list_allowed_roots")
    @export_tool(
        name="list_allowed_roots",
        logger=logging.getLogger(__name__),
        tags=["server.list_allowed_roots"],
    )
    async def list_allowed_roots(self, ctx: Context, constraints: dict | None = None) -> str:
        """Get a formatted list of all currently allowed root directories."""
        try:
            combined_roots = await dependencies.get_combined_roots(ctx)

            if not combined_roots:
                return "No allowed roots configured."

            lines = ["Allowed Root Directories:"]
            for i, root in enumerate(combined_roots, 1):
                source = "Server" if root in settings.ALLOWED_ROOTS else "Client"
                lines.append(f"{i}. {root} ({source})")

            return "\n".join(lines)
        except ToolOperationError:
            raise
        except Exception as e:
            raise ToolOperationError(
                "operation_failed",
                f"Failed to list allowed roots: {e}",
                actions=[
                    "Check the server and client root configuration.",
                    "Verify the context is valid.",
                    "Retry the operation.",
                ],
            ) from e

    @guard("server.add_allowed_root")
    @export_tool(
        name="add_allowed_root",
        logger=logging.getLogger(__name__),
        tags=["server.add_allowed_root"],
    )
    async def add_allowed_root(
        self, path: str, ctx: Context, constraints: dict | None = None
    ) -> str:
        """Add a path to the server's allowed roots whitelist at runtime."""
        try:
            path_obj = dependencies.check_path(path, check_existence=True)

            if not path_obj.is_dir():
                raise ToolOperationError(
                    "validation",
                    f"'{path}' is not a directory",
                    actions=[
                        "Provide a directory path.",
                        "Verify the path exists.",
                        "Retry with a valid directory.",
                    ],
                )

            if path_obj not in settings.ALLOWED_ROOTS:
                settings.ALLOWED_ROOTS.append(path_obj)
                return f"Successfully added '{path_obj}' to allowed roots."

            return f"Path '{path_obj}' is already in allowed roots."
        except ToolOperationError:
            raise
        except Exception as e:
            raise ToolOperationError(
                "operation_failed",
                f"Failed to add allowed root '{path}': {e}",
                actions=[
                    "Verify the path is accessible.",
                    "Check directory permissions.",
                    "Retry the operation.",
                ],
            ) from e

    @guard("server.update_roots")
    @export_tool(
        name="update_roots",
        logger=logging.getLogger(__name__),
        tags=["server.update_roots"],
    )
    async def update_roots(
        self, newroots: list[str], ctx: Context | None = None, constraints: dict | None = None
    ) -> str:
        """Update allowed roots from a list of paths.

        Args:
                ctx: List of new root paths
        """
        try:
            new_roots = []
            for p in newroots:
                try:
                    path_obj = dependencies.check_path(Path(p), check_existence=True)
                    if path_obj.is_dir():
                        new_roots.append(path_obj)
                    else:
                        raise ToolOperationError(
                            "validation",
                            f"Path '{p}' does not exist or is not a directory",
                            actions=[
                                "Provide only directory paths.",
                                "Verify the path exists.",
                                "Retry with valid directories.",
                            ],
                        )
                except ToolOperationError:
                    raise
                except Exception as e:
                    raise ToolOperationError(
                        "operation_failed",
                        f"Error processing path '{p}': {e}",
                        actions=[
                            "Verify the path is accessible.",
                            "Check directory permissions.",
                            "Retry with a valid path.",
                        ],
                    ) from e

            if not new_roots:
                raise ToolOperationError(
                    "validation",
                    "No valid directories provided",
                    actions=[
                        "Provide at least one valid directory.",
                        "Retry the operation.",
                    ],
                )

            settings.ALLOWED_ROOTS.clear()
            settings.ALLOWED_ROOTS.extend(new_roots)
            return f"Updated allowed roots to {len(new_roots)} directories"

        except ToolOperationError:
            raise
        except Exception as e:
            raise ToolOperationError(
                "operation_failed",
                f"Failed to update allowed roots: {e}",
                actions=[
                    "Verify all paths are accessible directories.",
                    "Check directory permissions.",
                    "Retry the operation.",
                ],
            ) from e

    @guard("server.remove_root")
    @export_tool(
        name="remove_root",
        logger=logging.getLogger(__name__),
        tags=["server.remove_root"],
    )
    async def remove_root(
        self, root: str, ctx: Context | None = None, constraints: dict | None = None
    ) -> str:
        """Remove a single allowed root path."""
        try:
            path_obj = dependencies.check_path(Path(root), check_existence=True)
            if not path_obj.is_dir():
                raise ToolOperationError(
                    "validation",
                    f"Path '{root}' is not a directory",
                    actions=[
                        "Provide a directory path.",
                        "Verify the path exists.",
                        "Retry with a valid directory.",
                    ],
                )

            if path_obj not in settings.ALLOWED_ROOTS:
                raise ToolOperationError(
                    "not_found",
                    f"Root '{root}' not found in allowed roots",
                    actions=[
                        "Check the current allowed roots list.",
                        "Verify the root path is correct.",
                        "Retry with an existing allowed root.",
                    ],
                )

            settings.ALLOWED_ROOTS.remove(path_obj)
            return f"Removed root '{root}'"
        except ToolOperationError:
            raise
        except (TypeError, ValueError, OSError) as exc:
            raise ToolOperationError(
                "validation",
                f"Error processing path '{root}': {exc}",
                actions=[
                    "Provide a valid directory path.",
                    "Verify the path syntax.",
                    "Retry with a valid path.",
                ],
            ) from exc
        except Exception as exc:
            raise ToolOperationError(
                "operation_failed",
                f"Error removing root '{root}': {exc}",
                actions=[
                    "Verify the allowed roots configuration.",
                    "Check directory permissions.",
                    "Retry the operation.",
                ],
            ) from exc

    @guard("server.submit_error_report")
    @export_tool(
        name="submit_error_report",
        logger=logging.getLogger(__name__),
        tags=["server.submit_error_report"],
    )
    async def submit_error_report(
        self,
        summary: str,
        ctx: Context,
        error_id: str | None = None,
        reproduction_steps: str | None = None,
        system_info: str | None = None,
        attachments: list[str] | None = None,
    ) -> str:
        """Collect technical error details from users for diagnostics and support.

        Args:
                summary: Short description of the problem.
                error_id: Optional error ID returned by server.
                reproduction_steps: Optional reproduction steps.
                system_info: Optional environment details provided by user.
                attachments: Optional list of file names or references.
        """
        request_id = log_context.request_id_ctx.get()
        trace_id = log_context.trace_id_ctx.get()
        user_id = log_context.user_id_ctx.get()
        operation = log_context.operation_ctx.get()

        report_id = save_error_report(
            summary=summary,
            error_id=error_id,
            reproduction_steps=reproduction_steps,
            system_info=system_info,
            attachments=attachments,
            request_id=request_id,
            trace_id=trace_id,
            user_id=user_id,
            operation=operation,
        )

        return (
            f"Report submitted successfully. report_id={report_id}. "
            f"trace_id={trace_id}. Please share this report ID with support if follow-up is needed."
        )
