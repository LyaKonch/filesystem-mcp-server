from __future__ import annotations

import ctypes
import logging
import os
from typing import TYPE_CHECKING

from fastmcp import Context

from auth.permissions import guard
from core_tools.BaseSystemManager import BaseSystemManager, EnvScope
from utilities.decorators import export_tool
from utilities.error_handling import ToolOperationError

if TYPE_CHECKING:
    from windows.ProcessManager import ProcessManager as WindowsProcessManager
    from windows.RegistryManager import RegistryManager as WindowsRegistryManager


class SystemManager(BaseSystemManager):
    """Windows specific manager that handles system-level operations. This is a place for any general operations that don't fit into other categories, but are still related to the system itself, not processes, services or filesystem, etc. For example environment variables management, updates and so on. If some operation requires multiple low-level managers, it can be implemented here as well.
    Also, when os has some component, that other os doesnt have( for example registry for windows that linux has no analog for), its functionality can be facaded here as well."
    """

    USER_ENV_PATH = r"Environment"
    SYS_ENV_PATH = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"

    def __init__(self, registry_mgr: WindowsRegistryManager, process_mgr: WindowsProcessManager):
        self.logger = logging.getLogger(__name__)
        self.registry = registry_mgr
        self.process_mgr = process_mgr

    def _broadcast_env_change(self):
        """Sends a system-wide message to notify other applications of environment variable changes. This is necessary for changes to take effect without requiring a user logout or system restart."""
        try:
            ctypes.windll.user32.SendMessageTimeoutW(
                0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, ctypes.byref(ctypes.c_ulong())
            )
        except Exception as e:
            self.logger.warning(f"Failed to broadcast env change: {e}")

    @guard("system.get_environment_variable")
    @export_tool(
        name="get_environment_variable",
        logger=logging.getLogger(__name__),
        tags=["system.get_environment_variable"],
    )
    def get_variable(
        self,
        ctx: Context,
        name: str,
        scope: EnvScope = EnvScope.USER,
        constraints: dict | None = None,
    ) -> dict | str | None:
        self._validate_key_name(name)
        if scope == EnvScope.PROCESS:
            return os.environ.get(name)

        hive = "HKEY_CURRENT_USER" if scope == EnvScope.USER else "HKEY_LOCAL_MACHINE"
        path = self.USER_ENV_PATH if scope == EnvScope.USER else self.SYS_ENV_PATH

        try:
            result = self.registry.read_registry_key(hive, path, name)
            if isinstance(result, dict) and "value" in result:
                return result
        except ToolOperationError:
            raise
        except Exception as e:
            raise ToolOperationError(
                "operation_failed",
                f"Failed to read environment variable from registry: {name} in {hive}\\{path}",
                actions=[
                    "Verify the environment variable exists.",
                    "Check registry access permissions.",
                    "Retry the operation.",
                ],
            ) from e
        return None

    @guard("system.list_environment_variables")
    @export_tool(
        name="list_environment_variables",
        logger=logging.getLogger(__name__),
        tags=["system.list_environment_variables"],
    )
    def list_variables(
        self, ctx: Context, scope: EnvScope = EnvScope.USER, constraints: dict | None = None
    ) -> dict[str, str]:
        if scope == EnvScope.PROCESS:
            return dict(os.environ)

        hive = "HKEY_CURRENT_USER" if scope == EnvScope.USER else "HKEY_LOCAL_MACHINE"
        path = self.USER_ENV_PATH if scope == EnvScope.USER else self.SYS_ENV_PATH

        result = self.registry.list_registry_key(hive, path)
        if isinstance(result, dict) and "values" in result:
            return {k: v["value"] for k, v in result["values"].items()}
        return {}

    @guard("system.set_environment_variable")
    @export_tool(
        name="set_environment_variable",
        logger=logging.getLogger(__name__),
        tags=["system.set_environment_variable"],
    )
    async def set_variable(
        self,
        ctx: Context,
        name: str,
        value: str,
        scope: EnvScope = EnvScope.USER,
        constraints: dict | None = None,
    ) -> str:
        self._validate_key_name(name)

        os.environ[name] = value

        if scope == EnvScope.PROCESS:
            return f"Set process environment variable '{name}' to '{value}'"

        hive = "HKEY_CURRENT_USER" if scope == EnvScope.USER else "HKEY_LOCAL_MACHINE"
        path = self.USER_ENV_PATH if scope == EnvScope.USER else self.SYS_ENV_PATH

        try:
            res = await self.registry.write_registry_key(
                ctx, hive, path, name, value, 1
            )  # winreg.REG_SZ
            self._broadcast_env_change()
            return res
        except ToolOperationError:
            raise
        except Exception as e:
            raise ToolOperationError(
                "operation_failed",
                f"Failed to write environment variable to registry: {name} in {hive}\\{path}",
                actions=[
                    "Verify registry write permissions.",
                    "Check that you have administrator privileges.",
                    "Ensure the registry path is valid.",
                    "Retry the operation.",
                ],
            ) from e

    @guard("system.delete_environment_variable")
    @export_tool(
        name="delete_environment_variable",
        logger=logging.getLogger(__name__),
        tags=["system.delete_environment_variable"],
    )
    async def delete_variable(
        self,
        ctx: Context,
        name: str,
        scope: EnvScope = EnvScope.USER,
        constraints: dict | None = None,
    ) -> str:
        self._validate_key_name(name)

        if name in os.environ:
            del os.environ[name]

        if scope == EnvScope.PROCESS:
            return f"Deleted process environment variable '{name}'"

        hive = "HKEY_CURRENT_USER" if scope == EnvScope.USER else "HKEY_LOCAL_MACHINE"
        path = self.USER_ENV_PATH if scope == EnvScope.USER else self.SYS_ENV_PATH

        try:
            res = await self.registry.delete_registry_key(ctx, hive, path, name)
            self._broadcast_env_change()
            return res
        except ToolOperationError:
            raise
        except Exception as e:
            raise ToolOperationError(
                "operation_failed",
                f"Failed to delete environment variable from registry: {name}",
                actions=[
                    "Verify registry write permissions.",
                    "Check that you have administrator privileges.",
                    "Ensure the environment variable exists.",
                    "Retry the operation.",
                ],
            ) from e

    @guard("system.create_windows_restore_point")
    @export_tool(name="create_windows_restore_point", tags=["system.create_windows_restore_point"])
    async def create_restore_point(
        self,
        ctx: Context,
        description: str,
        restore_point_type: str = "MODIFY_SETTINGS",
        constraints: dict | None = None,
    ) -> str:
        """Creates a new System Restore point.
        Command used: powershell.exe -Command Checkpoint-Computer -Description "Name" -RestorePointType "APPLICATION_INSTALL"
         - Description: A string describing the restore point. This will help identify the restore point
        Note: Requires Administrator privileges and 'System Protection' must be enabled.
        """
        valid_types = [
            "APPLICATION_INSTALL",
            "APPLICATION_UNINSTALL",
            "DEVICE_DRIVER_INSTALL",
            "MODIFY_SETTINGS",
        ]
        if restore_point_type not in valid_types:
            restore_point_type = "MODIFY_SETTINGS"
        ps_command = [
            "powershell.exe",
            "-Command",
            f"Checkpoint-Computer -Description '{description}' -RestorePointType '{restore_point_type}' -ErrorAction Stop",
        ]

        self.logger.info(f"Creating restore point: {description}")

        try:
            result = await self.process_mgr._run_raw_command(*ps_command, use_shell=False)
            return f"Restore point creation triggered: {result}"
        except ToolOperationError:
            raise
        except Exception as e:
            raise ToolOperationError(
                "operation_failed",
                f"Failed to create restore point '{description}'",
                actions=[
                    "Verify you have administrator privileges.",
                    "Check that System Protection is enabled on the system.",
                    "Ensure there is sufficient disk space for the restore point.",
                    "Review Windows System Protection settings.",
                    "Retry the operation.",
                ],
            ) from e

    # def add_open_extension_from_context_window():
    #     pass

    # def add_program_to_autorun(self):
    #     pass

    # def delete_program_from_autorun(self):
    #     pass

    # def check_for_updates():
    #     pass
