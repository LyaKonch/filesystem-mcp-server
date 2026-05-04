from __future__ import annotations

from typing import TYPE_CHECKING

from core_tools.OSManager import BaseOSManager

if TYPE_CHECKING:
    from linux.FilesystemManager import FilesystemManager as LinuxFilesystemManager
    from linux.ProcessManager import ProcessManager as LinuxProcessManager
    from linux.ServiceManager import ServiceManager as LinuxServiceManager
    from linux.SystemManager import SystemManager as LinuxSystemManager


class LinuxOSManager(
    BaseOSManager[
        LinuxProcessManager, LinuxServiceManager, LinuxFilesystemManager, LinuxSystemManager
    ]
):
    def __init__(self, process_mgr, service_mgr, fs_mgr, system_mgr):
        super().__init__(process_mgr, service_mgr, fs_mgr, system_mgr)
