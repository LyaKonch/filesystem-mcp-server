from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastmcp import Context

from auth.permissions import guard
from core_tools.OSManager import BaseOSManager
from utilities.decorators import export_tool
from utilities.dependencies import validate_path

if TYPE_CHECKING:
    from windows.FilesystemManager import FilesystemManager as WindowsFilesystemManager
    from windows.ProcessManager import ProcessManager as WindowsProcessManager
    from windows.ServiceManager import ServiceManager as WindowsServiceManager
    from windows.SystemManager import SystemManager as WindowsSystemManager


class WindowsOSManager(BaseOSManager):
    def __init__(
        self,
        process_mgr: WindowsProcessManager,
        service_mgr: WindowsServiceManager,
        fs_mgr: WindowsFilesystemManager,
        system_mgr: WindowsSystemManager,
    ):
        super().__init__(process_mgr, service_mgr, fs_mgr, system_mgr)
        self.logger = logging.getLogger(__name__)
        self.service_mgr = service_mgr
        self.process_mgr = service_mgr.process_mgr
        self.system_mgr = system_mgr
        self.registry = system_mgr.registry

    @guard("windowsos.backup_registry_keys")
    @export_tool(
        name="backup_registry_keys",
        logger=logging.getLogger(__name__),
        tags=["windowsos.backup_registry_keys"],
    )
    async def backup_registry_keys(
        self,
        ctx: Context,
        hive: str,
        sub_key: str,
        output_path: str,
        constraints: dict | None = None,
    ) -> str:
        """Exports a registry keys to a .reg file (readable text format) using 'reg export' command."""
        # For example: reg export "HKEY_CURRENT_USER\Environment" "C:\backup.reg" /y

        await self.registry.check_key_exists(ctx, hive, sub_key)

        try:
            await validate_path(output_path, ctx=ctx, must_exist=False, expected_type="file")
        except Exception as e:
            return f"Unexpected error when validating output path: {e}"
        full_key = f"{hive}\\{sub_key}"

        command = ["reg", "export", full_key, output_path, "/y"]

        self.logger.info(f"Exporting registry key {full_key} to {output_path}")

        result = await self.process_mgr._run_raw_command(*command, use_shell=False)
        return result

    @guard("windowsos.restore_registry_keys_from_file")
    @export_tool(
        name="restore_registry_keys_from_file",
        logger=logging.getLogger(__name__),
        tags=["windowsos.restore_registry_keys_from_file"],
    )
    async def restore_backup(self, ctx: Context, file_path: str, constraints: dict | None = None):
        """Restores registry keys from a .reg file using 'reg import' command. The .reg file should be in the format exported by backup_registry_keys."""
        try:
            await validate_path(file_path, ctx=ctx, must_exist=True, expected_type="file")
        except Exception as e:
            return f"Unexpected error when validating output path: {e}"
        self.logger.info(f"Importing registry key from {file_path}")
        return await self.process_mgr._run_raw_command("reg", "import", file_path)
