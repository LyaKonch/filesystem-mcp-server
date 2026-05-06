# here should be functions related to dangerous operations on the system, e.g. executing commands, restarting the server
# etc. that require special permissions and should be used with caution.
# These functions can be registered as tools in the MCP server and protected with authentication and authorization checks to ensure they are only accessible to trusted clients.
from __future__ import annotations

import platform
from abc import ABC

from core_tools.BaseFilesystemManager import BaseFilesystemManager
from core_tools.BaseProcessManager import BaseProcessManager
from core_tools.BaseServiceManager import BaseServiceManager
from core_tools.BaseSystemManager import BaseSystemManager


class BaseOSManager(ABC):
    """This is a composition class that specifically implements complex operations that may involve multiple managers. Also higher level interface for registering tools, because it has access to all managers.
    One time dependency injection in manager is allowed( for example process_mgr into service_mgr), but is not a great design choice, because it may lead to tight coupling and circular imports. Should always keep single responsibility principle in mind and try to keep managers as independent as possible.
    Ideally there should be couple of low-level managers that are used between higher one and higher-level's managers should never directly depend on each other. If so, that's a sign to create another low-level one, that will be later leveraged, or move logic to OSManager.
    """

    def __init__(
        self,
        process_mgr: BaseProcessManager,
        service_mgr: BaseServiceManager,
        fs_mgr: BaseFilesystemManager,
        system_mgr: BaseSystemManager,
    ):
        self.processes = process_mgr
        self.services = service_mgr
        self.filesystem = fs_mgr
        self.system = system_mgr


def create_os_manager() -> BaseOSManager:
    current_os = platform.system()

    if current_os == "Windows":
        from windows.FilesystemManager import FilesystemManager as WindowsFilesystemManager
        from windows.OSManager import WindowsOSManager
        from windows.ProcessManager import ProcessManager as WindowsProcessManager
        from windows.RegistryManager import RegistryManager as WindowsRegistryManager
        from windows.ServiceManager import ServiceManager as WindowsServiceManager
        from windows.SystemManager import SystemManager as WindowsSystemManager

        win_process_mgr: WindowsProcessManager = WindowsProcessManager()
        win_fs_mgr: WindowsFilesystemManager = WindowsFilesystemManager()
        win_registry_mgr: WindowsRegistryManager = WindowsRegistryManager()

        win_service_mgr: WindowsServiceManager = WindowsServiceManager(win_process_mgr)
        win_system_manager: WindowsSystemManager = WindowsSystemManager(
            win_registry_mgr, win_process_mgr
        )

        return WindowsOSManager(win_process_mgr, win_service_mgr, win_fs_mgr, win_system_manager)
    elif current_os == "Linux":
        from linux.FilesystemManager import FilesystemManager as LinuxFilesystemManager
        from linux.OSManager import LinuxOSManager
        from linux.ProcessManager import ProcessManager as LinuxProcessManager
        from linux.ServiceManager import ServiceManager as LinuxServiceManager
        from linux.SystemManager import SystemManager as LinuxSystemManager

        linux_process_mgr: LinuxProcessManager = LinuxProcessManager()
        linux_service_mgr: LinuxServiceManager = LinuxServiceManager()  # type: ignore[abstract]
        linux_fs_mgr: LinuxFilesystemManager = LinuxFilesystemManager()
        linux_system_mgr: LinuxSystemManager = LinuxSystemManager()  # type: ignore[abstract]
        return LinuxOSManager(linux_process_mgr, linux_service_mgr, linux_fs_mgr, linux_system_mgr)
    else:
        raise NotImplementedError(f"OS {current_os} is not supported")
