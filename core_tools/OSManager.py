# here should be functions related to dangerous operations on the system, e.g. executing commands, restarting the server
# etc. that require special permissions and should be used with caution.
# These functions can be registered as tools in the MCP server and protected with authentication and authorization checks to ensure they are only accessible to trusted clients.
import platform

from core_tools.BaseFilesystemManager import BaseFilesystemManager
from core_tools.BaseProcessManager import BaseProcessManager
from core_tools.BaseServiceManager import BaseServiceManager


class OSManager:
    def __init__(
        self,
        process_mgr: BaseProcessManager,
        service_mgr: BaseServiceManager,
        fs_mgr: BaseFilesystemManager,
    ):
        self.processes = process_mgr
        self.services = service_mgr
        self.filesystem = fs_mgr


def create_os_manager() -> OSManager:
    current_os = platform.system()
    process_mgr: BaseProcessManager
    service_mgr: BaseServiceManager
    fs_mgr: BaseFilesystemManager

    if current_os == "Windows":
        from windows.FilesystemManager import FilesystemManager as WindowsFilesystemManager
        from windows.ProcessManager import ProcessManager as WindowsProcessManager
        from windows.ServiceManager import ServiceManager as WindowsServiceManager

        process_mgr = WindowsProcessManager()
        service_mgr = WindowsServiceManager()
        fs_mgr = WindowsFilesystemManager()

    elif current_os == "Linux":
        from linux.FilesystemManager import FilesystemManager as LinuxFilesystemManager
        from linux.ProcessManager import ProcessManager as LinuxProcessManager
        from linux.ServiceManager import ServiceManager as LinuxServiceManager

        process_mgr = LinuxProcessManager()
        service_mgr = LinuxServiceManager()
        fs_mgr = LinuxFilesystemManager()
    else:
        raise NotImplementedError(f"OS {current_os} is not supported")
    return OSManager(process_mgr, service_mgr, fs_mgr)
