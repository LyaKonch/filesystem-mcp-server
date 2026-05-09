import asyncio
import logging
from contextlib import asynccontextmanager

import psutil
import win32api
import win32con
import win32job
import win32process

from config import settings
from core_tools.BaseProcessManager import BaseProcessManager
from utilities.error_handling import ToolOperationError


class ProcessManager(BaseProcessManager):
    "Windows-specific implementation of the ProcessManager"

    "Access control in Windows is super complicated, so for the sake of simplicity this manager will try to execute some operation on process, without checking permissions beforehand."
    "Basically, user that launched this server, are allowed to kill processes that he own, but not processes owned by other users or system processes."
    "If access is denied or process not found, it will simply say either 'Access Denied' or 'Process Not Found'"
    "With all said above, it makes sense to launch server with either least privileged user, or with admin privileges, depending on use case and security considerations."

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self._job_handle = win32job.CreateJobObject(None, "MCP_SERVER_JOB")

        global_limits = win32job.QueryInformationJobObject(
            self._job_handle, win32job.JobObjectExtendedLimitInformation
        )

        global_limits["BasicLimitInformation"]["LimitFlags"] = (
            win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            | win32job.JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            | win32job.JOB_OBJECT_LIMIT_JOB_MEMORY
        )

        global_limits["BasicLimitInformation"]["ActiveProcessLimit"] = (
            settings.WINDOWS_NUMBER_OF_PROCESSES_LIMIT
        )
        global_limits["JobMemoryLimit"] = settings.WINDOWS_MEMORY_LIMIT_PROCESSES_MB * 1024 * 1024

        win32job.SetInformationJobObject(
            self._job_handle, win32job.JobObjectExtendedLimitInformation, global_limits
        )

    def __del__(self):
        """Guaranteed cleanup of job object and all processes associated with it when ProcessManager instance is destroyed, which should happen when server is stopped or restarted."""

        # Closing the job handle will automatically terminate all processes associated with it due to the JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if hasattr(self, "_job_handle") and self._job_handle:
            try:
                self.logger.info("Closing global Job Object handle...")
                win32api.CloseHandle(self._job_handle)
            except Exception as e:
                self.logger.error(f"Error closing global job handle: {e}")

    def _get_subprocess_kwargs(self, use_shell: bool) -> dict:
        """On windows we create the process suspended, so we can add it to the Job Object."""
        return {"creationflags": win32process.CREATE_SUSPENDED | win32process.CREATE_NO_WINDOW}

    @asynccontextmanager
    async def _process_lifecycle(self, process: asyncio.subprocess.Process):
        main_thread = psutil.Process(process.pid).threads()[0].id

        # setup before lifecycle. in windows we need to create a Job Object and assign process to it
        local_job_handle = self._put_process_in_job_object(process.pid, main_thread)
        try:
            # passing in base class for reading stdout/stderr
            yield
        finally:
            # after process finishes, we need to close the job handle to clean up
            if local_job_handle:
                try:
                    win32api.CloseHandle(local_job_handle)
                except Exception as e:
                    raise Exception(f"Failed to close local job handle: {e}") from e

    def _put_process_in_job_object(self, pid: int, thread_id: int):
        try:
            process = win32api.OpenProcess(win32con.PROCESS_ALL_ACCESS, False, pid)

            local_job_handle = win32job.CreateJobObject(None, "")

            local_limits = win32job.QueryInformationJobObject(
                local_job_handle, win32job.JobObjectExtendedLimitInformation
            )

            local_limits["BasicLimitInformation"]["LimitFlags"] = (
                win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | win32job.JOB_OBJECT_LIMIT_JOB_MEMORY
            )
            local_limits["JobMemoryLimit"] = (
                settings.WINDOWS_MEMORY_LIMIT_PER_PROCESS_MB * 1024 * 1024
            )

            win32job.SetInformationJobObject(
                local_job_handle, win32job.JobObjectExtendedLimitInformation, local_limits
            )

            # so called nested jobs, windows under the hood will build hierarchy of jobs, but for us it is transparent,
            # we just assign process to both local and global job object
            # global jobs will control numbers of processes and overall memory usage and local jobs will control local memory usage
            if hasattr(self, "_job_handle") and self._job_handle:
                win32job.AssignProcessToJobObject(self._job_handle, process)
            win32job.AssignProcessToJobObject(local_job_handle, process)

            thread_handle = win32api.OpenThread(win32con.THREAD_SUSPEND_RESUME, False, thread_id)
            win32process.ResumeThread(thread_handle)

            win32api.CloseHandle(thread_handle)
            win32api.CloseHandle(process)

            self.logger.info(f"Process {pid} assigned to job object successfully.")
            return local_job_handle
        except Exception as e:
            self.logger.warning(f"Failed to assign process {pid} to job object: {e}")
            raise ToolOperationError(
                "operation_failed",
                f"Failed to assign process {pid} to job object: {e}",
                actions=[
                    "Check process permissions and existence.",
                    "Ensure the server has necessary privileges.",
                    "Retry the operation.",
                ],
            ) from e
