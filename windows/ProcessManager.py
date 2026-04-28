import asyncio
import logging
from contextvars import ContextVar

import psutil
from fastmcp import Context

from core_tools.BaseProcessManager import BaseProcessManager
            stdout, stderr = await asyncio.wait_for(
                asyncio.gather(
                    self._read_stream(process.stdout), self._read_stream(process.stderr)
                ),
                timeout=timeout_sec,
            )
    "tracert": ["tracert"],
}

current_mcp_ctx: ContextVar[Context | None] = ContextVar("current_mcp_ctx", default=None)


class ProcessManager(BaseProcessManager):
    "Windows-specific implementation of the ProcessManager"

    "Access control in Windows is super complicated, so for the sake of simplicity this manager will try to execute some operation on process, without checking permissions beforehand."
    "Basically, user that launched this server, are allowed to kill processes that he own, but not processes owned by other users or system processes."
    "If access is denied or process not found, it will simply say either 'Access Denied' or 'Process Not Found'"
    "With all said above, it makes sense to launch server with either least privileged user, or with admin privileges, depending on use case and security considerations."

    def __init__(self):
        # self.os_manager = os_manager
        self.logger = logging.getLogger(__name__)

    @export_tool(
        name="start_process", logger=logging.getLogger(__name__), tags=["process_management"]
    )
    async def start_process(
        self, command: str, ctx: Context, command_args: list[str] | None = None
    ) -> str:
        """Initiate a new process based on a specified command with optional arguments.
        Validates the command against an allowed list, constructs the full command with arguments, and executes it asynchronously while capturing output and errors for logging and response.
        Args:
            command: The base command to execute (e.g., 'ping').
            command_args: Optional list of additional arguments for the command (e.g., ['google.com'])."""
        current_mcp_ctx.set(ctx)
        if command not in commands:
            return f"Command '{command}' is not available."

        command_args = command_args or []
        full_args = commands[command] + command_args

        if command == "restart_server":
            pass  # custom logic for restarting server, etc
            #  in list should be not only commands itself, but also markers for special handling

        return await self._run_raw_command(*full_args, use_shell=False)

    # @require_admin
    @export_tool(
        name="run_admin_shell", logger=logging.getLogger(__name__), tags=["process_management"]
    )
    async def run_admin_shell(self, raw_command: str, ctx: Context) -> str:
        """
        [DANGEROUS] Execute a raw shell command with pipes and redirects.
        Admin use only.
        """
        current_mcp_ctx.set(ctx)
        return await self._run_raw_command(raw_command, use_shell=True)

    @export_tool(
        name="get_available_commands",
        logger=logging.getLogger(__name__),
        tags=["process_management"],
    )
    async def get_available_commands(
        self,
    ) -> dict[str, list[str] | str]:
        """Get a list of available commands that can be executed with start_process."""
        return commands

    async def _run_raw_command(self, *args: str, use_shell: bool = False) -> str:
        try:
            CREATE_NO_WINDOW = 0x08000000
            timeout_sec = 60
            if use_shell:
                raw_command = args[0] if args else ""
                process = await asyncio.create_subprocess_shell(
                    raw_command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    creationflags=CREATE_NO_WINDOW,
                )
                self.logger.info(f"Started shell command: {raw_command}, pid={process.pid}")
            else:
                process = await asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    creationflags=CREATE_NO_WINDOW,
                )

                self.logger.info(f"Started exec: {args}, pid={process.pid}")

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

    async def _read_stream(self, stream: asyncio.StreamReader) -> str:
        result_str: list[str] = []
        ctx = current_mcp_ctx.get()
        async for line in stream:
            decoded_line = line.decode(errors="replace").strip()
            if ctx:
                await ctx.info(decoded_line)
            result_str.append(decoded_line)
        return "\n".join(result_str)

    @export_tool(
        name="kill_process", logger=logging.getLogger(__name__), tags=["process_management"]
    )
    async def kill_process(
        self, ctx: Context, process_id=None, name=None, username=None, started_ts=None
    ):
        "Kill a process by its PID with elicitation support. Use this method preferably to confirm the action explicitly"
        try:
            if psutil.Process().pid == process_id:
                self.logger.warning(
                    f"Attempt to kill the server process (PID {process_id}) was blocked."
                )
                return f"Error: Cannot terminate the server process itself (PID {process_id}). Operation aborted."

            process = psutil.Process(process_id)
            summary = super()._build_process_summary(process)

            if not checkElicitationCapability(ctx.session):
                self.logger.warning(
                    f"No elicitation support to confirm termination for process {process_id}."
                )

                await ctx.error(
                    f"Cannot terminate process {process_id} due to lack of elicitation capability."
                )
                await ctx.info("Checking process details to confirm the action...")

                if (
                    summary["pid"] != process_id
                    or summary["name"] != name
                    or summary["username"] != username
                    or summary["started_ts"] != started_ts
                ):
                    self.logger.error(f"Process {process_id} does not match the provided criteria.")
                    return f"Process {process_id} does not match the provided criteria. Termination aborted. If you really want to terminate this process, please call this instrument with parameters that corresponds to process you want to kill."

                process.terminate()
                self.logger.info(f"Process {process_id} terminated successfully.")

                return f"Process {process_id} terminated successfully."

            user_agreed = await ctx.elicit(
                f"Are you sure you want to terminate '{summary}'? ", bool
            )
            if not user_agreed:
                self.logger.info(f"User declined to terminate process {process_id}.")
                return f"Process {process_id} termination cancelled by user."

            process.terminate()
            self.logger.info(f"Process {process_id} terminated successfully.")

            return f"Process {process_id} terminated successfully."

        except psutil.NoSuchProcess:
            self.logger.warning(f"Process {process_id} not found.")
            return f"Process {process_id} not found."
        except psutil.AccessDenied:
            self.logger.warning(f"Access denied when trying to access process {process_id}.")
            return f"Access denied when trying to access process {process_id}."
        except Exception as e:
            self.logger.warning(f"Failed to terminate process {process_id}: {e}")
            return f"Failed to terminate process {process_id}: {e}"

    @export_tool(
        name="suspend_process", logger=logging.getLogger(__name__), tags=["process_management"]
    )
    async def suspend_process(
        self,
        ctx: Context,
        process_id=None,
        name=None,
        username=None,
        started_ts=None,
    ):
        """
        Suspend a running process by PID. On Windows this has the effect of suspending all process threads.

        Use this to pause a process without terminating it, for example when
        you need to inspect state or temporarily stop execution during
        troubleshooting.
        """
        try:
            if psutil.Process().pid == process_id:
                self.logger.warning(
                    f"Attempt to suspend the server process (PID {process_id}) was blocked."
                )
                return f"Error: Cannot suspend the server process itself (PID {process_id}). Operation aborted."

            process = psutil.Process(process_id)
            summary = super()._build_process_summary(process)

            if not checkElicitationCapability(ctx.session):
                self.logger.warning(
                    f"No elicitation support to confirm suspension for process {process_id}."
                )

                await ctx.error(
                    f"Cannot suspend process {process_id} due to lack of elicitation capability."
                )
                await ctx.info("Checking process details to confirm the action...")

                if (
                    summary["pid"] != process_id
                    or summary["name"] != name
                    or summary["username"] != username
                    or summary["started_ts"] != started_ts
                ):
                    self.logger.error(f"Process {process_id} does not match the provided criteria.")
                    return (
                        f"Process {process_id} does not match the provided criteria. Suspension aborted. "
                        "If you really want to suspend this process, please call this instrument with "
                        "parameters that corresponds to process you want to suspend."
                    )

                process.suspend()
                self.logger.info(
                    f"Process {process_id} ({summary['name']}) suspended successfully."
                )
                return f"Process {process_id} ({summary['name']}) suspended successfully."

            user_agreed = await ctx.elicit(f"Are you sure you want to suspend '{summary}'? ", bool)
            if not user_agreed:
                self.logger.info(f"User declined to suspend process {process_id}.")
                return f"Process {process_id} suspension cancelled by user."

            process.suspend()

            self.logger.info(f"Process {process_id} ({summary['name']}) suspended successfully.")
            return f"Process {process_id} ({summary['name']}) suspended successfully."

        except psutil.NoSuchProcess:
            self.logger.warning(f"Process {process_id} not found.")
            return f"Process {process_id} not found."
        except psutil.AccessDenied:
            self.logger.warning(f"Access denied when trying to suspend process {process_id}.")
            return f"Access denied when trying to suspend process {process_id}."
        except Exception as e:
            self.logger.warning(f"Failed to suspend process {process_id}: {e}")
            return f"Failed to suspend process {process_id}: {e}"

    @export_tool(
        name="resume_process", logger=logging.getLogger(__name__), tags=["process_management"]
    )
    async def resume_process(
        self,
        ctx: Context,
        process_id=None,
        name=None,
        username=None,
        started_ts=None,
    ):
        """Resume a previously suspended process by PID.

        Use this to continue execution after a deliberate suspend during
        diagnostics or temporary throttling.
        """
        try:
            if psutil.Process().pid == process_id:
                self.logger.warning(
                    f"Attempt to resume the server process (PID {process_id}) was blocked."
                )
                return f"Error: Cannot resume the server process itself (PID {process_id}). Operation aborted."

            process = psutil.Process(process_id)
            summary = super()._build_process_summary(process)

            if not checkElicitationCapability(ctx.session):
                self.logger.warning(
                    f"No elicitation support to confirm resume for process {process_id}."
                )

                await ctx.error(
                    f"Cannot resume process {process_id} due to lack of elicitation capability."
                )
                await ctx.info("Checking process details to confirm the action...")

                if (
                    summary["pid"] != process_id
                    or summary["name"] != name
                    or summary["username"] != username
                    or summary["started_ts"] != started_ts
                ):
                    self.logger.error(f"Process {process_id} does not match the provided criteria.")
                    return (
                        f"Process {process_id} does not match the provided criteria. Resume aborted. "
                        "If you really want to resume this process, please call this instrument with "
                        "parameters that corresponds to process you want to resume."
                    )

                process.resume()
                self.logger.info(f"Process {process_id} ({summary['name']}) resumed successfully.")
                return f"Process {process_id} ({summary['name']}) resumed successfully."

            user_agreed = await ctx.elicit(f"Are you sure you want to resume '{summary}'? ", bool)
            if not user_agreed:
                self.logger.info(f"User declined to resume process {process_id}.")
                return f"Process {process_id} resume cancelled by user."

            process.resume()

            self.logger.info(f"Process {process_id} ({summary['name']}) resumed successfully.")
            return f"Process {process_id} ({summary['name']}) resumed successfully."

        except psutil.NoSuchProcess:
            self.logger.warning(f"Process {process_id} not found.")
            return f"Process {process_id} not found."
        except psutil.AccessDenied:
            self.logger.warning(f"Access denied when trying to resume process {process_id}.")
            return f"Access denied when trying to resume process {process_id}."
        except Exception as e:
            self.logger.warning(f"Failed to resume process {process_id}: {e}")
            return f"Failed to resume process {process_id}: {e}"
