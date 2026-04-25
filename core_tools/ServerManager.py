import logging
from pathlib import Path

from fastmcp import Context

from config import settings
from utilities import dependencies
from utilities import logging as log_context
from utilities.decorators import export_tool
from utilities.error_reports import save_error_report


class ServerManager:
    def __init__(self):
        self.module_logger = logging.getLogger(__name__)

    @export_tool(name="get_server_status", logger=logging.getLogger(__name__), tags=["management"])
    async def get_server_status(self, ctx: Context) -> dict:
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

    @export_tool(name="list_allowed_roots", logger=logging.getLogger(__name__), tags=["management"])
    async def list_allowed_roots(self, ctx: Context) -> str:
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
        except Exception as e:
            return f"Error: {str(e)}"

    @export_tool(
        name="add_allowed_root",
        logger=logging.getLogger(__name__),
        tags=["management", "admin"],
    )
    async def add_allowed_root(self, path: str, ctx: Context) -> str:
        """Add a path to the server's allowed roots whitelist at runtime."""
        try:
            path_obj = dependencies.check_path(path, check_existence=True)

            if not path_obj.is_dir():
                return f"Error: '{path}' is not a directory"

            if path_obj not in settings.ALLOWED_ROOTS:
                settings.ALLOWED_ROOTS.append(path_obj)
                return f"Successfully added '{path_obj}' to allowed roots."

            return f"Path '{path_obj}' is already in allowed roots."
        except Exception as e:
            return f"Error: {str(e)}"

    @export_tool(
        name="update_roots",
        logger=logging.getLogger(__name__),
        tags=["management", "admin"],
    )
    async def update_roots(self, newroots: list[str]) -> str:
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
                        return f"Error: Path '{p}' does not exist or is not a directory"
                except Exception as e:
                    return f"Error processing path '{p}': {str(e)}"

            if not new_roots:
                return "Error: No valid directories provided"

            settings.ALLOWED_ROOTS.clear()
            settings.ALLOWED_ROOTS.extend(new_roots)
            return f"Updated allowed roots to {len(new_roots)} directories"

        except Exception as e:
            return f"Error updating roots: {str(e)}"

    @export_tool(
        name="remove_root",
        logger=logging.getLogger(__name__),
        tags=["management", "admin"],
    )
    async def remove_root(self, root: str) -> str:
        """Remove a single allowed root path."""
        try:
            path_obj = dependencies.check_path(Path(root), check_existence=True)
            if not path_obj.is_dir():
                return f"Error: Path '{root}' is not a directory"

            if path_obj not in settings.ALLOWED_ROOTS:
                return f"Error: Root '{root}' not found in allowed roots"

            settings.ALLOWED_ROOTS.remove(path_obj)
            return f"Removed root '{root}'"
        except (TypeError, ValueError, OSError) as exc:
            return f"Error processing path '{root}': {str(exc)}"
        except Exception as exc:
            return f"Error removing root: {str(exc)}"

    @export_tool(
        name="submit_error_report",
        logger=logging.getLogger(__name__),
        tags=["management", "support"],
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
