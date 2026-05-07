import asyncio
import logging

import psutil
import win32api
import win32con
import win32job
import win32process
from fastmcp import Context
from fastmcp.dependencies import Depends

from auth.permissions import guard
from config import settings
from core_tools.BaseProcessManager import BaseProcessManager
from utilities.contextvar import current_mcp_ctx
from utilities.decorators import export_tool
from utilities.dependencies import request_elicitation_permission

commands: dict = {
    "restart_server": "restart_server",  # marker for special handling, not actual command to execute
    "ping": ["ping"],
    "tracert": ["tracert"],
    "servy-cli": [".\\windows\\bin\\servy\\./servy-cli"],
}


class ProcessManager(BaseProcessManager):
    "Windows-specific implementation of the ProcessManager"

    "Access control in Windows is super complicated, so for the sake of simplicity this manager will try to execute some operation on process, without checking permissions beforehand."
    "Basically, user that launched this server, are allowed to kill processes that he own, but not processes owned by other users or system processes."
    "If access is denied or process not found, it will simply say either 'Access Denied' or 'Process Not Found'"
    "With all said above, it makes sense to launch server with either least privileged user, or with admin privileges, depending on use case and security considerations."

    def __init__(self):
        # self.os_manager = os_manager
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

    @export_tool(
        name="start_process", logger=logging.getLogger(__name__), tags=["process.start_process"]
    )
    async def start_process(
        self,
        command: str,
        ctx: Context,
        command_args: list[str] | None = None,
        constraints: dict | None = Depends(guard("process.start_process")),
    ) -> str:
        """Initiate a new process based on a specified command with optional arguments.
        Validates the command against an allowed list, constructs the full command with arguments, and executes it asynchronously while capturing output and errors for logging and response.
        Args:
            command: The base command to execute (e.g., 'ping').
            command_args: Optional list of additional arguments for the command (e.g., ['google.com'])."""
        current_mcp_ctx.set(ctx)
        if command not in commands:
            raise ValueError(f"Command '{command}' is not available.")

        command_args = command_args or []
        full_args = commands[command] + command_args

        if command == "restart_server":
            pass  # custom logic for restarting server, etc
            #  in list should be not only commands itself, but also markers for special handling

        return await self._run_raw_command(*full_args, use_shell=False)

    # @require_admin
    @export_tool(
        name="run_admin_shell", logger=logging.getLogger(__name__), tags=["process.run_admin_shell"]
    )
    async def run_admin_shell(
        self,
        raw_command: str,
        ctx: Context,
        constraints: dict | None = Depends(guard("process.run_admin_shell")),
    ) -> str:
        """
        [DANGEROUS] Execute a raw shell command with pipes and redirects.
        Admin use only.
        """
        current_mcp_ctx.set(ctx)
        return await self._run_raw_command(raw_command, use_shell=True)

    @export_tool(
        name="get_available_commands",
        logger=logging.getLogger(__name__),
        tags=["process.get_available_commands"],
    )
    def get_available_commands(
        self, ctx: Context | None = None, constraints: dict | None = None
    ) -> dict[str, list[str] | str]:
        """Get a list of available commands that can be executed with start_process."""
        return commands

    async def _run_raw_command(self, *args: str, use_shell: bool = False) -> str:
        local_job_handle = None
        try:
            timeout_sec = 60
            if use_shell:
                raw_command = args[0] if args else ""
                process = await asyncio.create_subprocess_shell(
                    raw_command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    creationflags=win32process.CREATE_SUSPENDED | win32process.CREATE_NO_WINDOW,
                )
                self.logger.info(f"Started shell command: {raw_command}, pid={process.pid}")
            else:
                process = await asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    creationflags=win32process.CREATE_SUSPENDED | win32process.CREATE_NO_WINDOW,
                )

                self.logger.info(f"Started exec: {args}, pid={process.pid}")

            main_thread = psutil.Process(process.pid).threads()[0].id

            # we hang this variable here so it and child processes will be automatically cleaned up when process finishes
            local_job_handle = self._put_process_in_job_object(process.pid, main_thread)

            stdout, stderr = await asyncio.wait_for(
                asyncio.gather(
                    self._read_stream(process.stdout), self._read_stream(process.stderr)
                ),
                timeout=timeout_sec,
            )

            await process.wait()
            if process.returncode != 0:
                self.logger.error(
                    f"Process {args} failed with code {process.returncode}, pid={process.pid}"
                )
                return f"Process {args} failed with code {process.returncode}, pid={process.pid}, result: {stderr}"

            self.logger.info(
                f"Process {args} completed successfully with code {process.returncode}, pid={process.pid}"
            )
            return f"Process {args} completed successfully with code {process.returncode}, pid={process.pid}, result: {stdout}"
        except TimeoutError:
            # if process frozen
            process.kill()
            return f"Error: Command timed out after {timeout_sec} seconds."
        except FileNotFoundError:
            return f"Error: Command '{args[0]}' not found. Check if the program is installed and paths are correct."
        except Exception as e:
            return f"Unexpected error: {str(e)}"
        finally:
            if local_job_handle:
                win32api.CloseHandle(local_job_handle)

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

    async def _read_stream(self, stream) -> str:
        result_str: list[str] = []
        ctx = current_mcp_ctx.get()
        async for line in stream:
            decoded_line = line.decode(errors="replace").strip()
            if ctx:
                await ctx.info(decoded_line)
            result_str.append(decoded_line)
        return "\n".join(result_str)

    @export_tool(
        name="kill_process", logger=logging.getLogger(__name__), tags=["process.kill_process"]
    )
    async def kill_process(
        self,
        ctx: Context,
        process_id=None,
        name=None,
        username=None,
        started_ts=None,
        constraints: dict | None = Depends(guard("process.kill_process")),
    ):
        """Kill a process by its PID with elicitation support. Use this method preferably to confirm the action explicitly"""
        try:
            if psutil.Process().pid == process_id:
                raise ValueError(
                    f"Cannot terminate the server process itself (PID {process_id}). Operation aborted."
                )

            process = psutil.Process(process_id)
            summary = super()._build_process_summary(process)

            permission = await request_elicitation_permission(
                ctx, f"Are you sure you want to terminate '{summary}'?"
            )

            if permission is None:
                raise PermissionError(
                    "Cannot terminate process due to lack of elicitation capability. "
                    "Provide all process details (name, username, started_ts) to proceed without confirmation."
                )

            if permission is False:
                self.logger.info(f"User declined to terminate process {process_id}.")
                return f"Process {process_id} termination cancelled by user."

            process.terminate()
            self.logger.info(f"Process {process_id} terminated successfully.")

            return f"Process {process_id} terminated successfully."

        except psutil.NoSuchProcess as e:
            raise ValueError(f"Process {process_id} not found.") from e
        except psutil.AccessDenied as e:
            raise PermissionError(
                f"Access denied when trying to access process {process_id}."
            ) from e

    @export_tool(
        name="suspend_process", logger=logging.getLogger(__name__), tags=["process.suspend_process"]
    )
    async def suspend_process(
        self,
        ctx: Context,
        process_id=None,
        name=None,
        username=None,
        started_ts=None,
        constraints: dict | None = Depends(guard("process.suspend_process")),
    ):
        """
        Suspend a running process by PID. On Windows this has the effect of suspending all process threads.

        Use this to pause a process without terminating it, for example when
        you need to inspect state or temporarily stop execution during
        troubleshooting.
        """
        try:
            if psutil.Process().pid == process_id:
                raise ValueError(
                    f"Cannot suspend the server process itself (PID {process_id}). Operation aborted."
                )

            process = psutil.Process(process_id)
            summary = super()._build_process_summary(process)

            permission = await request_elicitation_permission(
                ctx, f"Are you sure you want to suspend '{summary}'?"
            )

            if permission is None:
                raise PermissionError(
                    "Cannot suspend process due to lack of elicitation capability. "
                    "Provide all process details (name, username, started_ts) to proceed without confirmation."
                )

            if permission is False:
                self.logger.info(f"User declined to suspend process {process_id}.")
                return f"Process {process_id} suspension cancelled by user."

            process.suspend()

            self.logger.info(f"Process {process_id} ({summary['name']}) suspended successfully.")
            return f"Process {process_id} ({summary['name']}) suspended successfully."

        except psutil.NoSuchProcess as e:
            raise ValueError(f"Process {process_id} not found.") from e
        except psutil.AccessDenied as e:
            raise PermissionError(
                f"Access denied when trying to suspend process {process_id}."
            ) from e

    @export_tool(
        name="resume_process", logger=logging.getLogger(__name__), tags=["process.resume_process"]
    )
    async def resume_process(
        self,
        ctx: Context,
        process_id=None,
        name=None,
        username=None,
        started_ts=None,
        constraints: dict | None = Depends(guard("process.resume_process")),
    ):
        """Resume a previously suspended process by PID.

        Use this to continue execution after a deliberate suspend during
        diagnostics or temporary throttling.
        """
        try:
            if psutil.Process().pid == process_id:
                raise ValueError(
                    f"Cannot resume the server process itself (PID {process_id}). Operation aborted."
                )

            process = psutil.Process(process_id)
            summary = super()._build_process_summary(process)

            permission = await request_elicitation_permission(
                ctx, f"Are you sure you want to resume '{summary}'?"
            )

            if permission is None:
                raise PermissionError(
                    "Cannot resume process due to lack of elicitation capability. "
                    "Provide all process details (name, username, started_ts) to proceed without confirmation."
                )

            if permission is False:
                self.logger.info(f"User declined to resume process {process_id}.")
                return f"Process {process_id} resume cancelled by user."

            process.resume()

            self.logger.info(f"Process {process_id} ({summary['name']}) resumed successfully.")
            return f"Process {process_id} ({summary['name']}) resumed successfully."

        except psutil.NoSuchProcess as e:
            raise ValueError(f"Process {process_id} not found.") from e
        except psutil.AccessDenied as e:
            raise PermissionError(
                f"Access denied when trying to resume process {process_id}."
            ) from e

    @export_tool(
        name="kill_process_tree",
        logger=logging.getLogger(__name__),
        tags=["process.kill_process_tree"],
    )
    async def kill_process_tree(
        self,
        ctx: Context,
        pid: int,
        constraints: dict | None = Depends(guard("process.kill_process_tree")),
    ) -> str:
        """
        Kill a process and all of its child processes recursively.
        Requires user confirmation. Protects server process from termination.

        Args:
            ctx: MCP Context for elicitation
            pid: The PID of the parent process to kill.

        Returns:
            Status message describing the operation result.

        Raises:
            ValueError: If pid is invalid or points to server process
            psutil.NoSuchProcess: If process not found
            psutil.AccessDenied: If access denied
        """
        try:
            server_pid = psutil.Process().pid
            if pid == server_pid:
                raise ValueError(f"Cannot terminate server process (PID {pid}). Operation aborted.")

            root_process = psutil.Process(pid)
            summary = super()._build_process_summary(root_process)

            permission = await request_elicitation_permission(
                ctx,
                f"Are you sure you want to terminate '{summary}' and ALL of its {len(root_process.children(recursive=True))} child processes? "
                "This action cannot be undone.",
            )

            if permission is None:
                raise PermissionError(
                    "Cannot terminate process tree due to lack of elicitation capability."
                )

            if permission is False:
                self.logger.info(f"User declined to terminate process tree rooted at {pid}.")
                return "Process tree termination cancelled by user."

            killed_count = 0
            failed = []

            # Kill children first (breadth-first to collect all descendants)
            def kill_children_recursive(parent_process: psutil.Process):
                nonlocal killed_count
                try:
                    children = parent_process.children(recursive=False)
                    for child in children:
                        if child.pid == server_pid:
                            self.logger.warning(
                                f"Skipped server process (PID {server_pid}) in tree termination."
                            )
                            continue
                        try:
                            # Recursively kill grandchildren first
                            kill_children_recursive(child)
                            # Then kill the child
                            child.terminate()
                            killed_count += 1
                            self.logger.info(
                                f"Terminated child process {child.pid} ({child.name()})."
                            )
                        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                            failed.append((child.pid, str(e)))
                            self.logger.warning(
                                f"Could not terminate child process {child.pid}: {e}"
                            )
                except Exception as e:
                    self.logger.warning(f"Error iterating children of {parent_process.pid}: {e}")

            # Kill descendants
            kill_children_recursive(root_process)

            # Finally kill the root
            try:
                root_process.terminate()
                killed_count += 1
                self.logger.info(f"Terminated root process {pid} ({root_process.name()}).")
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                failed.append((pid, str(e)))
                self.logger.warning(f"Could not terminate root process {pid}: {e}")

            result = f"Successfully terminated {killed_count} process(es)"
            if failed:
                result += f". Failed to terminate {len(failed)} process(es): {failed}"

            return result

        except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError, PermissionError) as e:
            self.logger.warning(f"Failed to terminate process tree rooted at {pid}: {e}")
            raise

    def __del__(self):
        """Guaranteed cleanup of job object and all processes associated with it when ProcessManager instance is destroyed, which should happen when server is stopped or restarted."""

        # Closing the job handle will automatically terminate all processes associated with it due to the JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if hasattr(self, "_job_handle") and self._job_handle:
            try:
                self.logger.info("Closing global Job Object handle...")
                win32api.CloseHandle(self._job_handle)
            except Exception as e:
                self.logger.error(f"Error closing global job handle: {e}")
