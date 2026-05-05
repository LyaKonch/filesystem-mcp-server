from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TYPE_CHECKING

import psutil
import pywintypes
import win32evtlog
import win32service
import win32serviceutil
import winerror
from fastmcp import Context

from core_tools.BaseServiceManager import BaseServiceManager
from utilities.contextvar import current_mcp_ctx
from utilities.decorators import export_tool
from utilities.dependencies import request_elicitation_permission, validate_path
from utilities.error_handling import ToolOperationError

if TYPE_CHECKING:
    from windows.ProcessManager import ProcessManager as WindowsProcessManager


class ServiceManager(BaseServiceManager):
    """Windows service management wrappers.

    This class provides safe, documented wrappers around win32service and
    win32serviceutil. Each function returns a human-readable string and
    handles common win32 errors (access denied, not found, already running).
    """

    def __init__(self, process_mgr: WindowsProcessManager):
        self.logger = logging.getLogger(__name__)
        self.process_mgr = process_mgr

    @export_tool(
        name="list_services",
        tags=["service", "list"],
    )
    async def list_services(
        self,
        name: str | None = None,
        status: str | None = None,
        pid: int | None = None,
        username: str | None = None,
        start_type: str | None = None,
        binpath: str | None = None,
        description: str | None = None,
    ):
        """
        List Windows services with optional filtering.

        Parameters (all optional, case-insensitive, substring matching):
            name: Service or display name
            status: 'running', 'stopped', 'paused', etc.
            pid: Process ID (exact match)
            username: Service account
            start_type: 'automatic', 'manual', 'disabled'
            binpath: Binary path
            description: Service description

        Returns:
            list[dict]: Service dicts with keys: name, display_name, status, start_type,
                        pid, username, binpath, description. Empty list on error.
        """

        def _sync():
            try:
                services = []
                f_name = name.lower() if name else None
                f_status = status.lower() if status else None
                f_username = username.lower() if username else None
                f_start_type = start_type.lower() if start_type else None
                f_binpath = binpath.lower() if binpath else None
                f_desc = description.lower() if description else None

                for service in psutil.win_service_iter():
                    try:
                        s = service.as_dict()
                    except Exception as e:
                        self.logger.warning(f"Failed to get info for service {service}: {e}")
                        continue

                    s_name = (s.get("name") or "").lower()
                    s_disp = (s.get("display_name") or "").lower()

                    if f_name and not (
                        f_name in s_name or s_name in f_name or f_name in s_disp or s_disp in f_name
                    ):
                        continue
                    if f_status and (s.get("status") or "").lower() != f_status:
                        continue
                    if pid is not None and s.get("pid") != pid:
                        continue
                    if f_username and (s.get("username") or "").lower() != f_username:
                        continue
                    if f_start_type and (s.get("start_type") or "").lower() != f_start_type:
                        continue
                    if f_binpath:
                        s_bin = (s.get("binpath") or "").lower()
                        if not (f_binpath in s_bin or s_bin in f_binpath):
                            continue
                    if f_desc:
                        s_description = (s.get("description") or "").lower()
                        if not (f_desc in s_description or s_description in f_desc):
                            continue

                    services.append(s)

                return services
            except Exception as e:
                raise ToolOperationError(
                    "unexpected",
                    f"Error occurred while listing services: {e}",
                    actions=[
                        "Verify the service name or filters.",
                        "Retry the request.",
                        "Check server logs for the root cause.",
                    ],
                ) from e

        return await asyncio.to_thread(_sync)

    @export_tool(
        name="get_service_status",
        tags=["service", "status"],
    )
    async def get_service_status(self, service_name: str):
        """Return status dict for a specified service. Use this tool when you need detailed info about a single service, and get_services when you want to list all services."""

        def _sync():
            try:
                service = psutil.win_service_get(service_name)
                return service.as_dict()
            except Exception as e:
                if "does not exist" in str(e).lower() or "not found" in str(e).lower():
                    raise ToolOperationError(
                        "not_found",
                        f"Service '{service_name}' was not found.",
                        actions=[
                            "Verify the service name with list_services.",
                            "Check whether the service is installed.",
                        ],
                    ) from e
                raise ToolOperationError(
                    "unexpected",
                    f"Error occurred while getting service status for {service_name}: {e}",
                    actions=[
                        "Retry the request.",
                        "Check server logs for the root cause.",
                    ],
                ) from e

        return await asyncio.to_thread(_sync)

    @export_tool(
        name="start_service",
        tags=["service", "control"],
    )
    async def start_service(self, service_name: str, args: list | None = None) -> str:
        """Start a service.

        Parameters:
        - service_name: short service name
        - args: optional list of arguments to pass on start (if supported)

        Returns a status string.
        """

        def _sync():
            try:
                win32serviceutil.StartService(service_name, args if args else None)
                return f"Signal to start service '{service_name}' sent successfully."
            except pywintypes.error as e:
                if e.winerror == winerror.ERROR_SERVICE_ALREADY_RUNNING:
                    return f"Service '{service_name}' is already running."
                elif e.winerror == 5:
                    raise ToolOperationError(
                        "access_denied",
                        f"Access Denied. Administrator privileges required to start '{service_name}'.",
                        actions=[
                            "Run the server with elevated privileges.",
                            "Use 'Run as Administrator' or equivalent.",
                        ],
                    ) from e
                raise ToolOperationError(
                    "operation_failed",
                    f"Failed to start service '{service_name}': {getattr(e, 'strerror', str(e))}",
                    actions=[
                        "Verify the service name.",
                        "Check service configuration.",
                        "Retry the request.",
                    ],
                ) from e

        return await asyncio.to_thread(_sync)

    @export_tool(
        name="stop_service",
        tags=["service", "control"],
    )
    async def stop_service(self, service_name: str) -> str:
        """Stop a running service.

        Parameters:
        - service_name: short service name

        Returns a status string.
        """

        def _sync():
            try:
                win32serviceutil.StopService(service_name)
                return f"Signal to stop service '{service_name}' sent successfully."
            except pywintypes.error as e:
                if e.winerror == winerror.ERROR_SERVICE_NOT_ACTIVE:
                    return f"Service '{service_name}' is not running."
                elif e.winerror == 5:
                    raise ToolOperationError(
                        "access_denied",
                        f"Access Denied. Administrator privileges required to stop '{service_name}'.",
                        actions=[
                            "Run the server with elevated privileges.",
                            "Use 'Run as Administrator' or equivalent.",
                        ],
                    ) from e
                raise ToolOperationError(
                    "operation_failed",
                    f"Failed to stop service '{service_name}': {getattr(e, 'strerror', str(e))}",
                    actions=[
                        "Verify the service name.",
                        "Check service configuration.",
                        "Retry the request.",
                    ],
                ) from e

        return await asyncio.to_thread(_sync)

    @export_tool(
        name="stop_service_with_deps",
        tags=["service", "control"],
    )
    async def stop_service_with_deps(self, service_name: str) -> str:
        """Stop service and its dependent services using win32serviceutil.StopService (runs in thread)."""

        def _sync():
            try:
                win32serviceutil.StopServiceWithDeps(service_name)
                return f"Service '{service_name}' stopped successfully."
            except pywintypes.error as e:
                if e.winerror == 5:
                    raise ToolOperationError(
                        "access_denied",
                        f"Access Denied. Administrator privileges required to stop '{service_name}' and dependencies.",
                        actions=[
                            "Run the server with elevated privileges.",
                            "Use 'Run as Administrator' or equivalent.",
                        ],
                    ) from e
                raise ToolOperationError(
                    "operation_failed",
                    f"Failed to stop service '{service_name}' and dependencies: {getattr(e, 'strerror', str(e))}",
                    actions=[
                        "Verify the service name.",
                        "Check that dependent services exist.",
                        "Retry the request.",
                    ],
                ) from e

        return await asyncio.to_thread(_sync)

    @export_tool(
        name="restart_service",
        tags=["service", "control"],
    )
    async def restart_service(self, service_name: str) -> str:
        """Restart a service (Stop + Start) — runs in thread."""

        def _sync():
            try:
                win32serviceutil.RestartService(service_name)
                return f"Service '{service_name}' restarted successfully."
            except pywintypes.error as e:
                if e.winerror == 5:
                    raise ToolOperationError(
                        "access_denied",
                        f"Access Denied. Administrator privileges required to restart '{service_name}'.",
                        actions=[
                            "Run the server with elevated privileges.",
                            "Use 'Run as Administrator' or equivalent.",
                        ],
                    ) from e
                raise ToolOperationError(
                    "operation_failed",
                    f"Failed to restart service '{service_name}': {getattr(e, 'strerror', str(e))}",
                    actions=[
                        "Verify the service name.",
                        "Check service configuration.",
                        "Retry the request.",
                    ],
                ) from e

        return await asyncio.to_thread(_sync)

    @export_tool(
        name="change_service_startup_type",
        tags=["service", "config"],
    )
    async def change_service_startup_type(self, service_name: str, startup_type: str) -> str:
        """Change service startup type.

        startup_type: one of 'automatic','manual','disabled'.
        """
        mapping = {
            "automatic": win32service.SERVICE_AUTO_START,
            "manual": win32service.SERVICE_DEMAND_START,
            "disabled": win32service.SERVICE_DISABLED,
        }
        if startup_type not in mapping:
            raise ToolOperationError(
                "validation",
                f"Invalid startup_type '{startup_type}'.",
                actions=[
                    "Use one of: 'automatic', 'manual', 'disabled'.",
                    "Retry with a valid startup type.",
                ],
            )

        # Delegate to change_service_config using SERVICE_NO_CHANGE for other params
        return await self.change_service_config(service_name=service_name, start_type=startup_type)

    @export_tool(
        name="change_service_config",
        tags=["service", "config"],
    )
    async def change_service_config(
        self,
        service_name: str,
        binary_path: str | None = None,
        display_name: str | None = None,
        start_type: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> str:
        """Change service configuration preserving unspecified fields.

        Parameters:
        - service_name: short name
        - binary_path: new binary path or None to keep
        - display_name: new display name or None to keep
        - start_type: 'automatic'|'manual'|'disabled' or None
        - username/password: service account (None keeps existing)
        """
        mapping = {
            "automatic": win32service.SERVICE_AUTO_START,
            "manual": win32service.SERVICE_DEMAND_START,
            "disabled": win32service.SERVICE_DISABLED,
        }

        # If start_type is not provided, instruct Windows to leave it unchanged
        new_start = win32service.SERVICE_NO_CHANGE
        if start_type:
            if start_type not in mapping:
                raise ToolOperationError(
                    "validation",
                    f"Invalid start_type '{start_type}'.",
                    actions=[
                        "Use one of: 'automatic', 'manual', 'disabled'.",
                        "Retry with a valid start type.",
                    ],
                )
            new_start = mapping[start_type]

        def _sync():
            hscm = None
            hs = None
            try:
                hscm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_ALL_ACCESS)
                hs = win32serviceutil.SmartOpenService(
                    hscm, service_name, win32service.SERVICE_ALL_ACCESS
                )

                # Use SERVICE_NO_CHANGE for numeric fields we don't want to touch and
                # None for string fields we don't want to touch. Windows will keep
                # existing values for those parameters.
                win32service.ChangeServiceConfig(
                    hs,
                    win32service.SERVICE_NO_CHANGE,  # serviceType - do not change
                    new_start,  # startType (or SERVICE_NO_CHANGE)
                    win32service.SERVICE_NO_CHANGE,  # errorControl - do not change
                    binary_path,  # binaryPath (None = do not change)
                    None,  # loadOrderGroup
                    0,  # tagId (reserved)
                    None,  # dependencies (None = do not change)
                    username,  # serviceStartName (None = do not change)
                    password,  # password (None = do not change)
                    display_name,  # displayName (None = do not change)
                )
                return f"Service '{service_name}' configuration updated."
            except pywintypes.error as e:
                if e.winerror == 5:
                    raise ToolOperationError(
                        "access_denied",
                        f"Access Denied. Administrator privileges required to change config for '{service_name}'.",
                        actions=[
                            "Run the server with elevated privileges.",
                            "Use 'Run as Administrator' or equivalent.",
                        ],
                    ) from e
                elif e.winerror == winerror.ERROR_SERVICE_DOES_NOT_EXIST:
                    raise ToolOperationError(
                        "not_found",
                        f"Service '{service_name}' was not found.",
                        actions=[
                            "Verify the service name with list_services.",
                            "Check whether the service is installed.",
                        ],
                    ) from e
                raise ToolOperationError(
                    "operation_failed",
                    f"Failed to update config for '{service_name}': {getattr(e, 'strerror', str(e))}",
                    actions=[
                        "Verify the service name.",
                        "Check the configuration parameters.",
                        "Retry the request.",
                    ],
                ) from e
            finally:
                try:
                    if hs:
                        win32service.CloseServiceHandle(hs)
                    if hscm:
                        win32service.CloseServiceHandle(hscm)
                except Exception:
                    pass

        return await asyncio.to_thread(_sync)

    @export_tool(
        name="get_service_logs", logger=logging.getLogger(__name__), tags=["service_management"]
    )
    async def get_service_logs(
        self, service_name: str, source_name: str | None = None, max_records: int = 50
    ) -> list:
        """
        Return recent Application Event Log entries for a given service using the modern Event Log API.

        Args:
            service_name: The name of the service to find logs for.
            source_name: (Optional) Explicitly specify the Event Source Name.
                         If not provided, the tool will try to match the service_name,
                         or look for logs from wrapper tools (like 'Servy') that mention the service.
            max_records: Maximum number of recent entries to return.
        """

        def _sync():
            results = []
            try:
                if source_name:
                    xpath_query = f"*[System[Provider[@Name='{source_name}']]]"
                else:
                    xpath_query = f"*[System[Provider[@Name='{service_name}'] or Provider[@Name='Servy'] or Provider[@Name='Servy.Service']]]"

                flags = win32evtlog.EvtQueryChannelPath | win32evtlog.EvtQueryReverseDirection
                query_handle = win32evtlog.EvtQuery("Application", flags, xpath_query, None)

                ns = {"e": "http://schemas.microsoft.com/win/2004/08/events/event"}

                while len(results) < max_records:
                    events = win32evtlog.EvtNext(query_handle, 10, 1000, 0)
                    if not events:
                        break

                    for ev in events:
                        if len(results) >= max_records:
                            break

                        xml_str = win32evtlog.EvtRender(ev, win32evtlog.EvtRenderEventXml)

                        try:
                            root = ET.fromstring(xml_str)
                            src = root.find(".//e:Provider", ns).get("Name", "")
                            event_id = root.find(".//e:EventID", ns).text
                            time_created = root.find(".//e:TimeCreated", ns).get("SystemTime", "")
                            level = root.find(".//e:Level", ns).text
                        except Exception as e:
                            self.logger.warning(f"Failed to parse Event XML: {e}")
                            continue

                        try:
                            msg = win32evtlog.EvtFormatMessage(
                                None, ev, win32evtlog.EvtFormatMessageEvent
                            )
                        except Exception:
                            data_nodes = root.findall(".//e:EventData/e:Data", ns)
                            if data_nodes:
                                msg = " | ".join([node.text for node in data_nodes if node.text])
                            else:
                                user_data = root.find(".//e:UserData", ns)
                                if user_data is not None:
                                    msg = "".join(user_data.itertext()).strip()
                                else:
                                    msg = "<unformatted event>"

                        is_match = False

                        if not source_name and "servy" in src.lower():
                            if (
                                service_name.lower() in msg.lower()
                                or service_name.lower() in xml_str.lower()
                            ):
                                is_match = True
                        else:
                            is_match = True

                        if not is_match:
                            continue

                        results.append(
                            {
                                "time": time_created,
                                "source": src,
                                "event_id": int(event_id) if event_id else 0,
                                "event_type": int(level)
                                if level
                                else 0,  # 1=Critical, 2=Error, 3=Warning, 4=Info
                                "message": msg.strip(),
                            }
                        )

            except Exception as e:
                raise ToolOperationError(
                    "unexpected",
                    f"Failed to read event log for service '{service_name}': {e}",
                    actions=[
                        "Verify the service name.",
                        "Check whether event log is accessible.",
                        "Retry the request.",
                    ],
                ) from e

            return results

        return await asyncio.to_thread(_sync)

    @export_tool(
        name="create_service",
        tags=["service", "create"],
    )
    async def create_service(
        self,
        ctx: Context,
        service_name: str,
        display_name: str,
        binary_path: str,
        start_type: str = "manual",
        username: str | None = None,
        password: str | None = None,
    ) -> str:
        """
        Create a new Windows service. This tool only works for real services, that was specifically designed as windows service.
        Services with random or user binaries may be installed, but they might not or won't start.

        start_type: 'automatic'|'manual'|'disabled'
        """
        current_mcp_ctx.set(ctx)
        mapping = {
            "automatic": win32service.SERVICE_AUTO_START,
            "manual": win32service.SERVICE_DEMAND_START,
            "disabled": win32service.SERVICE_DISABLED,
        }
        if start_type not in mapping:
            raise ToolOperationError(
                "validation",
                f"Invalid start_type '{start_type}'.",
                actions=[
                    "Use one of: 'automatic', 'manual', 'disabled'.",
                    "Retry with a valid start type.",
                ],
            )

        permission = await request_elicitation_permission(
            ctx,
            f"Are you sure you want to create service '{service_name}' with binary path '{binary_path}'?",
        )

        if permission is None:
            raise ToolOperationError(
                "auth_required",
                "Cannot create service due to lack of elicitation capability.",
                actions=[
                    "Ensure elicitation is enabled in the server configuration.",
                    "Retry the request.",
                ],
            )

        if permission is False:
            self.logger.info(f"User declined to create service '{service_name}'.")
            return "Service creation cancelled by user."

        def _sync():
            hscm = None
            hs = None
            try:
                hscm = win32service.OpenSCManager(
                    None, None, win32service.SC_MANAGER_CREATE_SERVICE
                )
                hs = win32service.CreateService(
                    hscm,
                    service_name,
                    display_name,
                    win32service.SERVICE_ALL_ACCESS,
                    win32service.SERVICE_WIN32_OWN_PROCESS,
                    mapping[start_type],
                    win32service.SERVICE_ERROR_NORMAL,
                    binary_path,
                    None,
                    0,
                    None,
                    username,
                    password,
                )
                win32service.CloseServiceHandle(hs)
                return f"Service '{service_name}' created successfully."
            except pywintypes.error as e:
                if e.winerror == 5:
                    raise ToolOperationError(
                        "access_denied",
                        "Access Denied. Administrator privileges required to create service.",
                        actions=[
                            "Run the server with elevated privileges.",
                            "Use 'Run as Administrator' or equivalent.",
                        ],
                    ) from e
                elif e.winerror == winerror.ERROR_SERVICE_EXISTS:
                    raise ToolOperationError(
                        "operation_failed",
                        f"Service '{service_name}' already exists.",
                        actions=[
                            "Use a different service name.",
                            "Or delete the existing service first.",
                        ],
                    ) from e
                raise ToolOperationError(
                    "operation_failed",
                    f"Failed to create service '{service_name}': {getattr(e, 'strerror', str(e))}",
                    actions=[
                        "Verify the service configuration.",
                        "Check the binary path validity.",
                        "Retry the request.",
                    ],
                ) from e
            finally:
                try:
                    if hscm:
                        win32service.CloseServiceHandle(hscm)
                except Exception:
                    pass

        return await asyncio.to_thread(_sync)

    @export_tool(
        name="delete_service",
        tags=["service", "delete"],
    )
    async def delete_service(self, ctx: Context, service_name: str) -> str:
        """Delete an installed service. Requires user confirmation. It's recommended to stop the service first if it's running."""
        current_mcp_ctx.set(ctx)

        permission = await request_elicitation_permission(
            ctx,
            f"Are you sure you want to delete service '{service_name}'? This cannot be undone.",
        )

        if permission is None:
            raise ToolOperationError(
                "auth_required",
                "Cannot delete service due to lack of elicitation capability.",
                actions=[
                    "Ensure elicitation is enabled in the server configuration.",
                    "Retry the request.",
                ],
            )

        if permission is False:
            self.logger.info(f"User declined to delete service '{service_name}'.")
            return "Service deletion cancelled by user."

        def _sync():
            win32serviceutil.RemoveService(service_name)
            return f"Service '{service_name}' removed successfully."

        try:
            return await asyncio.to_thread(_sync)
        except pywintypes.error as e:
            if e.winerror == winerror.ERROR_SERVICE_DOES_NOT_EXIST:
                raise ToolOperationError(
                    "not_found",
                    f"Service '{service_name}' does not exist (or already deleted).",
                    actions=[
                        "Verify the service name with list_services.",
                        "Check whether the service is installed.",
                    ],
                ) from e
            elif e.winerror == winerror.ERROR_SERVICE_MARKED_FOR_DELETE:
                raise ToolOperationError(
                    "operation_failed",
                    f"Service '{service_name}' is already marked for deletion. It will disappear once stopped.",
                    actions=[
                        "Wait for the service to stop and be removed.",
                        "Or check the service status with get_service_status.",
                    ],
                ) from e
            elif e.winerror == 5:
                raise ToolOperationError(
                    "access_denied",
                    f"Access Denied. Administrator privileges required to delete '{service_name}'.",
                    actions=[
                        "Run the server with elevated privileges.",
                        "Use 'Run as Administrator' or equivalent.",
                    ],
                ) from e
            raise ToolOperationError(
                "operation_failed",
                f"Failed to remove service '{service_name}': {getattr(e, 'strerror', str(e))}",
                actions=[
                    "Verify the service name.",
                    "Check whether the service can be deleted.",
                    "Retry the request.",
                ],
            ) from e

    @export_tool(
        name="wrap_script_as_service",
        logger=logging.getLogger(__name__),
        tags=["service_management"],
    )
    async def wrap_script_as_service(
        self,
        ctx: Context,
        service_name: str,
        executor_path: str,
        script_path: str,
        display_name: str | None = None,
        start_type: str = "Automatic",
        stdout_path: str | None = None,
        stderr_path: str | None = None,
    ) -> str:
        """
        Wrap any script (Python, Node, etc.) as a background Windows service using Servy.

        Args:
            service_name: The internal name of the service (no spaces).
            executor_path: The executable to run the script (e.g., 'python.exe' or 'node.exe').
            script_path: The path to the script file.
            display_name: Friendly name for the Windows Services console.
            start_type: 'Automatic', 'AutomaticDelayedStart', 'Manual', or 'Disabled'.
            stdout_path: (Optional) Path to save the standard output logs.
            stderr_path: (Optional) Path to save the standard error logs.
        """
        current_mcp_ctx.set(ctx)

        try:
            abs_script_path = await validate_path(
                script_path, ctx, must_exist=True, expected_type="file"
            )
            stdout_path_result: str | Path | None = stdout_path
            if stdout_path is not None:
                stdout_path_result = await validate_path(
                    stdout_path, ctx, must_exist=False, expected_type="file"
                )
            stderr_path_result: str | Path | None = stderr_path
            if stderr_path is not None:
                stderr_path_result = await validate_path(
                    stderr_path, ctx, must_exist=False, expected_type="file"
                )
        except ValueError as e:
            self.logger.error(f"Script path validation failed: {e}")
            return f"Error: Script path validation failed: {e}"

        if not stdout_path_result:
            stdout_path_result = f"{abs_script_path}.stdout.log"
        if not stderr_path_result:
            stderr_path_result = f"{abs_script_path}.stderr.log"

        args = [
            "install",
            f"--name={service_name}",
            f"--path={executor_path}",
            f"--params={abs_script_path}",
            f"--startupType={start_type}",
            f"--stdout={stdout_path_result}",
            f"--stderr={stderr_path_result}",
            "--enableSizeRotation",
            "--rotationSize=10",
            "--enableHealth",
            "--recoveryAction=RestartProcess",
        ]

        if display_name:
            args.append(f"--displayName={display_name}")

        self.logger.info(
            f"Wrapping {abs_script_path} as service '{service_name}'. Logs will be saved to {stdout_path_result}"
        )

        full_command = self.process_mgr.get_available_commands().get("servy-cli", []) + args

        result = await self.process_mgr._run_raw_command(*full_command, use_shell=False)

        return result
