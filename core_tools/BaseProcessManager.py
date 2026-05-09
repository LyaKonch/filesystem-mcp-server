import asyncio
import logging
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager

import psutil
from fastmcp import Context
from fastmcp.dependencies import Depends

from auth.permissions import get_github_user_id, guard
from auth.PolicyManager import policy_manager
from utilities import dependencies
from utilities.contextvar import current_mcp_ctx
from utilities.decorators import export_tool
from utilities.dependencies import request_elicitation_permission
from utilities.error_handling import ToolOperationError


class BaseProcessManager(ABC):
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    @abstractmethod
    def _get_subprocess_kwargs(self, use_shell: bool) -> dict:
        pass

    @asynccontextmanager
    async def _process_lifecycle(self, process: asyncio.subprocess.Process):
        """Wraps the process lifecycle."""
        yield

    @export_tool(
        name="run_admin_shell", logger=logging.getLogger(__name__), tags=["process.run_admin_shell"]
    )
    async def run_admin_shell(
        self,
        raw_command: str,
        ctx: Context,
        timeout: int = 60,
        constraints: dict | None = Depends(guard("process.run_admin_shell")),
    ) -> str:
        """
        [DANGEROUS] Execute a raw shell command with pipes and redirects.
        Admin use only.
        timeout: Maximum time in seconds to allow the process to run before timing out.
        """
        current_mcp_ctx.set(ctx)
        max_allowed_timeout = constraints.get("max_timeout", 600)
        if "max_timeout" in constraints and not policy_manager.check_constraint(
            constraints, "max_timeout", max_allowed_timeout
        ):
            raise ToolOperationError(
                "invalid_input",
                f"Requested timeout {timeout}s exceeds maximum allowed {constraints['max_timeout']}s.",
                actions=[
                    "Reduce the requested timeout to be within allowed limits.",
                    "Check the policy constraints for maximum timeout.",
                    "Contact administrator if you believe this is an error.",
                ],
            )
        actual_timeout = min(timeout, max_allowed_timeout)
        return await self._run_raw_command(raw_command, use_shell=True, timeout=actual_timeout)

    @export_tool(
        name="start_process", logger=logging.getLogger(__name__), tags=["process.start_process"]
    )
    async def start_process(
        self,
        command: str,
        ctx: Context,
        command_args: list[str] | None = None,
        timeout: int = 60,
        constraints: dict | None = Depends(guard("process.start_process")),
    ) -> str:
        """Initiate a new process based on a specified command with optional arguments.
        Validates the command against an allowed list, constructs the full command with arguments, and executes it asynchronously while capturing output and errors for logging and response.
        Args:
            command: The base command to execute (e.g., 'ping').
            command_args: Optional list of additional arguments for the command (e.g., ['google.com']).
            timeout: Maximum time in seconds to allow the process to run before timing out.
            On windows all commands starts with NO_CREATE_WINDOW flag, so they will not create new gui window and may end immediately after execution.
        """
        current_mcp_ctx.set(ctx)
        if "allowed_commands" in constraints and not policy_manager.check_constraint(
            constraints, "allowed_commands", command
        ):
            raise ToolOperationError(
                "access_denied",
                f"Command '{command}' is not in your allowed commands list.",
                actions=[
                    "Verify the command is correct.",
                    "Check your permissions and allowed commands list.",
                    "Contact administrator if you believe this is an error.",
                ],
            )
        max_allowed_timeout = constraints.get("max_timeout", 600)
        if "max_timeout" in constraints and not policy_manager.check_constraint(
            constraints, "max_timeout", max_allowed_timeout
        ):
            raise ToolOperationError(
                "invalid_input",
                f"Requested timeout {timeout}s exceeds maximum allowed {constraints['max_timeout']}s.",
                actions=[
                    "Reduce the requested timeout to be within allowed limits.",
                    "Check the policy constraints for maximum timeout.",
                    "Contact administrator if you believe this is an error.",
                ],
            )
        actual_timeout = min(timeout, max_allowed_timeout)
        command_args = command_args or []
        full_args = [command] + command_args

        if command == "restart_server":
            pass  # custom logic for restarting server, etc
            #  in list should be not only commands itself, but also markers for special handling

        return await self._run_raw_command(*full_args, use_shell=False, timeout=actual_timeout)

    async def _run_raw_command(self, *args: str, use_shell: bool = False, timeout: int = 60) -> str:
        try:
            kwargs = self._get_subprocess_kwargs(use_shell)
            if use_shell:
                raw_command = args[0] if args else ""
                process = await asyncio.create_subprocess_shell(
                    raw_command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    **kwargs,
                )
                self.logger.info(f"Started shell command: {raw_command}, pid={process.pid}")
            else:
                process = await asyncio.create_subprocess_exec(
                    *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, **kwargs
                )

                self.logger.info(f"Started exec: {args}, pid={process.pid}")

            async with self._process_lifecycle(process):
                stdout, stderr = await asyncio.wait_for(
                    asyncio.gather(
                        self._read_stream(process.stdout), self._read_stream(process.stderr)
                    ),
                    timeout=timeout,
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
        except TimeoutError as e:
            # if process frozen
            process.kill()
            raise ToolOperationError(
                "timeout",
                f"Command timed out after {timeout} seconds.",
                actions=[
                    "Try reducing the scope of the command.",
                    "Check server performance and load.",
                    "Consider running a less resource-intensive command.",
                ],
            ) from e
        except FileNotFoundError as e:
            raise ToolOperationError(
                "not_found",
                f"Command '{args[0]}' not found. Check if the program is installed and paths are correct.",
                actions=[
                    "Verify the command and its arguments are correct.",
                    "Ensure the required software is installed on the server.",
                    "Check environment variables and PATH settings.",
                ],
            ) from e
        except Exception as e:
            raise ToolOperationError(
                "unexpected",
                f"Error executing command: {e}",
                actions=["Check server logs for more details."],
            ) from e

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
        name="get_available_commands",
        logger=logging.getLogger(__name__),
        tags=["process.get_available_commands"],
    )
    def get_available_commands(
        self,
        ctx: Context | None = None,
        constraints: dict | None = Depends(guard("process.get_available_commands")),
    ) -> dict[str, list[str] | str] | str:
        """Get a list of available commands that can be executed with start_process."""
        try:
            commands = policy_manager.get_constraints(
                get_github_user_id() or "", "process.start_process"
            )["allowed_commands"]
            if not commands:
                raise
        except Exception as e:
            raise ToolOperationError(
                "not_found",
                "No available commands found.",
                actions=["Check the policy configuration for allowed commands."],
            ) from e

        return commands

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
            process = psutil.Process(process_id)

            self._check_process_action_constraints(process, constraints)
            summary = self._build_process_summary(process)

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
            process = psutil.Process(process_id)

            self._check_process_action_constraints(process, constraints)

            summary = self._build_process_summary(process)

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
            process = psutil.Process(process_id)

            self._check_process_action_constraints(process, constraints)

            summary = self._build_process_summary(process)

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
            pid: The PID of the parent process to kill.

        Returns:
            Status message describing the operation result.
        """
        try:
            root_process = psutil.Process(pid)

            self._check_process_action_constraints(root_process, constraints)

            try:
                all_processes = [root_process] + root_process.children(recursive=True)
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                raise ToolOperationError(
                    "validation", f"Cannot build process tree for PID {pid}: {e}"
                ) from e
            for proc in all_processes:
                self._check_process_action_constraints(proc, constraints)

            summary = self._build_process_summary(root_process)

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

    def _check_process_action_constraints(self, process: psutil.Process, constraints: dict):
        """Checks common constraints for process actions like kill/suspend/resume and raises ToolOperationError if any constraint is violated."""
        if not constraints:
            return

        if "require_own_process" in constraints and not policy_manager.check_constraint(
            constraints, "require_own_process", process.username()
        ):
            raise ToolOperationError(
                "access_denied",
                f"You can only modify your own processes. Process belongs to {process.username()}.",
                actions=[
                    "Verify you have permission to manage processes owned by other users.",
                    "Check your user permissions and the target process ownership.",
                    "Contact an administrator if you believe this is an error.",
                ],
            )

        if "protected_processes" in constraints and not policy_manager.check_constraint(
            constraints, "protected_processes", process.name()
        ):
            raise ToolOperationError(
                "access_denied",
                f"Process '{process.name()}' is protected and cannot be modified.",
                actions=[
                    "Verify the process name and your permissions.",
                    "Check the policy constraints for protected processes.",
                    "Contact an administrator if you believe this is an error.",
                ],
            )

        if process.pid == psutil.Process().pid:
            raise ToolOperationError("access_denied", "Cannot modify the server process itself.")

    # ============================================================================================
    @export_tool(
        name="list_processes", logger=logging.getLogger(__name__), tags=["process.list_processes"]
    )
    def list_processes(
        self,
        filters: dict[str, object] | None = None,
        sort_by: str = "pid",
        limit: int | None = None,
        offset: int = 0,
        ctx: Context | None = None,
        constraints: dict | None = Depends(guard("process.list_processes")),
    ) -> list[dict[str, object]] | str:
        """Return lightweight summaries for running processes.

        Use this as a fast discovery endpoint to find candidate PIDs before
        requesting deeper diagnostics with get_process_info or
        get_detailed_process_info.

        Args:
            filters: Optional dict for filtering results by process attributes.
                Example: {"name": "python.exe", "username": "analn"}
                Supported keys: pid, ppid, name, username, status

            sort_by: Sort results by process attribute. Default: "pid"
                Numeric sorts: pid, ppid, cpu_percent, memory_rss, started_ts, create_time_ts, num_threads
                String sorts: name, username, status
                Prefix with "-" for reverse order: "-memory_rss" sorts by memory descending
                Example: sort_by="-cpu_percent" sorts by CPU usage (highest first)

            limit: Maximum number of results to return. Default: None (return all)
                Example: limit=10 returns first 10 processes

            offset: Skip first N results before returning. Default: 0
                Combine with limit for pagination: offset=20, limit=10 returns results 21-30
                Example: offset=50 skips first 50 processes

        Returns:
            List of process summary dicts with keys: pid, ppid, name, username, status,
            started, started_ts, cpu_percent, memory_rss, memory_rss_str
        """
        try:
            process_info_list = []

            for process in psutil.process_iter():
                try:
                    process_info_list.append(self._build_process_summary(process))
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    continue
                except Exception as e:
                    logging.getLogger(__name__).warning(
                        "Skipping process %s during list_processes: %s",
                        getattr(process, "pid", "unknown"),
                        e,
                    )

            if filters:
                process_info_list = self._filter_processes(process_info_list, filters)

            process_info_list = self._sort_processes(process_info_list, sort_by)

            if offset:
                process_info_list = process_info_list[offset:]

            if limit is not None:
                process_info_list = process_info_list[:limit]

            return process_info_list

        except Exception as e:
            raise ToolOperationError(
                "unexpected",
                f"Error occurred while listing processes: {e}",
                actions=[
                    "Retry the request.",
                    "Check server logs for the root cause.",
                ],
            ) from e

    @export_tool(
        name="get_current_username",
        logger=logging.getLogger(__name__),
        tags=["process.get_current_username"],
    )
    def get_current_username(
        self,
        ctx: Context | None = None,
        constraints: dict | None = Depends(guard("process.get_current_username")),
    ):
        try:
            return psutil.Process().username()
        except Exception as e:
            raise ToolOperationError(
                "unexpected",
                f"Unable to get current user: {e}",
                actions=[
                    "Retry the request.",
                    "Check whether the current process can inspect its own user context.",
                ],
            ) from e

    @export_tool(
        name="get_process_info",
        logger=logging.getLogger(__name__),
        tags=["process.get_process_info"],
    )
    def get_process_info(
        self,
        pid: int,
        ctx: Context | None = None,
        constraints: dict | None = Depends(guard("process.get_process_info")),
    ) -> dict[str, object]:
        """Return an expanded snapshot for a single process PID.

        Includes summary fields plus executable path, command line, cwd,
        thread count, CPU time, and memory metrics.
        """
        try:
            process = psutil.Process(pid)

            return self._build_process_info(process)
        except Exception as e:
            if isinstance(e, psutil.NoSuchProcess):
                raise ToolOperationError(
                    "not_found",
                    f"Process {pid} was not found or is no longer running.",
                    actions=[
                        "Verify the PID with list_processes.",
                        "Retry the request for a currently running process.",
                    ],
                ) from e
            if isinstance(e, psutil.AccessDenied):
                raise ToolOperationError(
                    "access_denied",
                    f"Access denied while reading process {pid} information.",
                    actions=[
                        "Run the server with elevated privileges.",
                        "Try a process owned by the current user.",
                    ],
                ) from e
            raise ToolOperationError(
                "unexpected",
                f"Error occurred while fetching process info for {pid}: {e}",
                actions=[
                    "Retry the request.",
                    "Check server logs for the root cause.",
                ],
            ) from e

    @export_tool(
        name="get_detailed_process_info",
        logger=logging.getLogger(__name__),
        tags=["process.get_detailed_process_info"],
    )
    def get_detailed_process_info(
        self,
        pid: int,
        tree: bool = False,
        connections: bool = False,
        open_files: bool = False,
        ctx: Context | None = None,
        constraints: dict | None = Depends(guard("process.get_detailed_process_info")),
    ) -> dict[str, object]:
        """Return process info and optionally include deep diagnostic sections.

        Enable tree, connections, and open_files flags when you need a
        full troubleshooting payload for one PID.
        """
        try:
            process = psutil.Process(pid)
            result = self._build_process_info(process)

            if tree:
                result["tree"] = self.get_process_tree(pid)
            if connections:
                result["connections"] = self.get_process_connections(
                    pid, kind="inet", state=None, limit=None
                )
            if open_files:
                result["open_files"] = self.get_process_open_files(
                    pid, limit=None, include_deleted=False
                )

            return result
        except Exception as e:
            if isinstance(e, psutil.NoSuchProcess):
                raise ToolOperationError(
                    "not_found",
                    f"Process {pid} was not found or is no longer running.",
                    actions=[
                        "Verify the PID with list_processes.",
                        "Retry the request for a currently running process.",
                    ],
                ) from e
            if isinstance(e, psutil.AccessDenied):
                raise ToolOperationError(
                    "access_denied",
                    f"Access denied while reading detailed information for process {pid}.",
                    actions=[
                        "Run the server with elevated privileges.",
                        "Try a process owned by the current user.",
                    ],
                ) from e
            raise ToolOperationError(
                "unexpected",
                f"Error occurred while fetching detailed process info for {pid}: {e}",
                actions=[
                    "Retry the request.",
                    "Check server logs for the root cause.",
                ],
            ) from e

    @export_tool(
        name="get_process_connections",
        logger=logging.getLogger(__name__),
        tags=["process.get_process_connections"],
    )
    def get_process_connections(
        self,
        pid: int,
        kind: str | None = "inet",
        state: str | None = None,
        limit: int | None = None,
        ctx: Context | None = None,
        constraints: dict | None = Depends(guard("process.get_process_connections")),
    ) -> list[dict[str, object]]:
        """Return network connections opened by a process.

        Useful for inspecting listening ports, active remote endpoints,
        and protocol/socket state during connectivity investigations.
        """
        try:
            process = psutil.Process(pid)
            connections = []

            for connection in process.net_connections(kind=kind or "inet"):
                if state and connection.status != state:
                    continue

                connections.append(
                    {
                        "fd": connection.fd,
                        "family": connection.family.name
                        if hasattr(connection.family, "name")
                        else str(connection.family),
                        "type": connection.type,
                        "local_address": getattr(connection.laddr, "ip", None)
                        if connection.laddr
                        else None,
                        "local_port": getattr(connection.laddr, "port", None)
                        if connection.laddr
                        else None,
                        "remote_address": getattr(connection.raddr, "ip", None)
                        if connection.raddr
                        else None,
                        "remote_port": getattr(connection.raddr, "port", None)
                        if connection.raddr
                        else None,
                        "status": connection.status,
                    }
                )

                if limit is not None and len(connections) >= limit:
                    break

            return connections
        except Exception as e:
            if isinstance(e, psutil.NoSuchProcess):
                raise ToolOperationError(
                    "not_found",
                    f"Process {pid} was not found or is no longer running.",
                    actions=[
                        "Verify the PID with list_processes.",
                        "Retry the request for a currently running process.",
                    ],
                ) from e
            if isinstance(e, psutil.AccessDenied):
                raise ToolOperationError(
                    "access_denied",
                    f"Access denied while reading network connections for process {pid}.",
                    actions=[
                        "Run the server with elevated privileges.",
                        "Try a process owned by the current user.",
                    ],
                ) from e
            raise ToolOperationError(
                "unexpected",
                f"Error occurred while fetching process connections for {pid}: {e}",
                actions=[
                    "Retry the request.",
                    "Check server logs for the root cause.",
                ],
            ) from e

    @export_tool(
        name="get_process_tree",
        logger=logging.getLogger(__name__),
        tags=["process.get_process_tree"],
    )
    def get_process_tree(
        self,
        pid: int,
        up_to_parent: bool = True,
        down_to_children: bool = True,
        depth: int = 1,
        max_nodes: int = 100,
        ctx: Context | None = None,
        constraints: dict | None = Depends(guard("process.get_process_tree")),
    ) -> dict[str, object]:
        """Return parent/child relationships for a process.

        Use this to understand lineage, identify spawned workers,
        and trace process ownership with configurable depth limits.
        """
        try:
            root = psutil.Process(pid)
            tree = {
                "pid": root.pid,
                "name": root.name(),
                "status": root.status(),
                "parent": None,
                "children": [],
            }

            if up_to_parent:
                try:
                    parent = root.parent()
                    if parent is not None:
                        tree["parent"] = {
                            "pid": parent.pid,
                            "name": parent.name(),
                            "status": parent.status(),
                        }
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    tree["parent"] = None

            if down_to_children:

                def collect_children(process, current_depth):
                    if current_depth > depth or len(tree["children"]) >= max_nodes:
                        return []
                    nodes = []
                    try:
                        for child in process.children(recursive=False):
                            if len(tree["children"]) >= max_nodes:
                                break
                            node = {
                                "pid": child.pid,
                                "name": child.name(),
                                "status": child.status(),
                            }
                            node["children"] = collect_children(child, current_depth + 1)
                            nodes.append(node)
                            tree["children"].append(node)
                    except (psutil.AccessDenied, psutil.NoSuchProcess):
                        return []
                    return nodes

                collect_children(root, 1)

            return tree
        except Exception as e:
            if isinstance(e, psutil.NoSuchProcess):
                raise ToolOperationError(
                    "not_found",
                    f"Process {pid} was not found or is no longer running.",
                    actions=[
                        "Verify the PID with list_processes.",
                        "Retry the request for a currently running process.",
                    ],
                ) from e
            if isinstance(e, psutil.AccessDenied):
                raise ToolOperationError(
                    "access_denied",
                    f"Access denied while building the process tree for {pid}.",
                    actions=[
                        "Run the server with elevated privileges.",
                        "Try a process owned by the current user.",
                    ],
                ) from e
            raise ToolOperationError(
                "unexpected",
                f"Error occurred while fetching process tree for {pid}: {e}",
                actions=[
                    "Retry the request.",
                    "Check server logs for the root cause.",
                ],
            ) from e

    @export_tool(
        name="get_process_open_files",
        logger=logging.getLogger(__name__),
        tags=["process.get_process_open_files"],
    )
    def get_process_open_files(
        self,
        pid: int,
        limit: int | None = None,
        include_deleted: bool = False,
        ctx: Context | None = None,
        constraints: dict | None = Depends(guard("process.get_process_open_files")),
    ) -> list[dict[str, object]]:
        """Return files currently opened by a process.

        Helpful when diagnosing file locks, leaked descriptors,
        or suspicious access to specific paths.
        """
        try:
            process = psutil.Process(pid)
            files = []

            for open_file in process.open_files():
                path = open_file.path
                if not include_deleted and path.endswith(" (deleted)"):
                    continue

                files.append(
                    {
                        "path": path,
                        "fd": open_file.fd,
                    }
                )

                if limit is not None and len(files) >= limit:
                    break

            return files
        except Exception as e:
            if isinstance(e, psutil.NoSuchProcess):
                raise ToolOperationError(
                    "not_found",
                    f"Process {pid} was not found or is no longer running.",
                    actions=[
                        "Verify the PID with list_processes.",
                        "Retry the request for a currently running process.",
                    ],
                ) from e
            if isinstance(e, psutil.AccessDenied):
                raise ToolOperationError(
                    "access_denied",
                    f"Access denied while reading open files for process {pid}.",
                    actions=[
                        "Run the server with elevated privileges.",
                        "Try a process owned by the current user.",
                    ],
                ) from e
            raise ToolOperationError(
                "unexpected",
                f"Error occurred while fetching process open files for {pid}: {e}",
                actions=[
                    "Retry the request.",
                    "Check server logs for the root cause.",
                ],
            ) from e

    def is_process_running(self, process_id):
        return psutil.pid_exists(process_id)

    def _build_process_summary(self, process: psutil.Process) -> dict:
        try:
            with process.oneshot():
                try:
                    create_time = process.create_time()
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    create_time = None

                try:
                    cpu_percent = process.cpu_percent(interval=None)
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    cpu_percent = None

                try:
                    memory_info = process.memory_info()
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    memory_info = None

                try:
                    ppid = process.ppid()
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    ppid = None

                started = None
                if create_time is not None:
                    started = psutil._pprint_secs(create_time)

                memory_rss = None
                memory_rss_str = None
                if memory_info is not None:
                    memory_rss = memory_info.rss
                    memory_rss_str = dependencies.format_size(memory_rss)

                return {
                    "pid": process.pid,
                    "ppid": ppid,
                    "name": process.name(),
                    "username": process.username(),
                    "status": process.status(),
                    "started": started,
                    "started_ts": create_time,
                    "cpu_percent": cpu_percent,
                    "memory_rss": memory_rss,
                    "memory_rss_str": memory_rss_str,
                }
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            raise

    def _build_process_info(self, process: psutil.Process) -> dict:
        summary = self._build_process_summary(process)

        try:
            with process.oneshot():
                try:
                    summary["exe"] = process.exe()
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    summary["exe"] = None

                try:
                    summary["cmdline"] = process.cmdline()
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    summary["cmdline"] = []

                try:
                    summary["cwd"] = process.cwd()
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    summary["cwd"] = None

                try:
                    raw_create_time = process.create_time()
                    summary["create_time"] = psutil._pprint_secs(raw_create_time)
                    summary["create_time_ts"] = raw_create_time
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    summary["create_time"] = None
                    summary["create_time_ts"] = None

                try:
                    summary["num_threads"] = process.num_threads()
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    summary["num_threads"] = None

                try:
                    summary["cpu_times"] = process.cpu_times()._asdict()
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    summary["cpu_times"] = None

                cpu_times = summary.get("cpu_times")
                if isinstance(cpu_times, dict):
                    summary["cpu_times_str"] = {
                        key: self._format_duration_seconds(value)
                        for key, value in cpu_times.items()
                        if isinstance(value, (int, float))
                    }
                else:
                    summary["cpu_times_str"] = None

                try:
                    summary["memory_info"] = process.memory_info()._asdict()
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    summary["memory_info"] = None

                memory_info = summary.get("memory_info")
                if isinstance(memory_info, dict):
                    memory_keys = {
                        "rss",
                        "vms",
                        "peak_wset",
                        "wset",
                        "peak_paged_pool",
                        "paged_pool",
                        "peak_nonpaged_pool",
                        "nonpaged_pool",
                        "pagefile",
                        "peak_pagefile",
                        "private",
                        "uss",
                        "pss",
                        "swap",
                        "data",
                        "text",
                        "lib",
                        "dirty",
                    }
                    summary["memory_info_str"] = {
                        key: dependencies.format_size(value)
                        for key, value in memory_info.items()
                        if key in memory_keys and isinstance(value, (int, float))
                    }

                    memory_rss = memory_info.get("rss")
                    summary["memory_rss"] = memory_rss
                    summary["memory_rss_str"] = (
                        dependencies.format_size(memory_rss)
                        if isinstance(memory_rss, (int, float))
                        else None
                    )
                else:
                    summary["memory_info_str"] = None

                return summary
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            raise

    def _filter_processes(self, process_list: list[dict], filters) -> list[dict]:
        if not filters or not isinstance(filters, dict):
            return process_list

        active_filters = {k: v for k, v in filters.items() if v is not None}

        if not active_filters:
            return process_list

        filtered = []

        for p in process_list:
            match = True

            for key, expected_value in active_filters.items():
                if p.get(key) != expected_value:
                    match = False
                    break

            if match:
                filtered.append(p)

        return filtered

    def _sort_processes(self, process_list: list[dict], sort_by: str) -> list[dict]:
        if not sort_by:
            return process_list

        reverse = False
        key = sort_by
        if isinstance(sort_by, str) and sort_by.startswith("-"):
            reverse = True
            key = sort_by[1:]

        numeric_sort_keys = {
            "pid",
            "ppid",
            "cpu_percent",
            "memory_rss",
            "started_ts",
            "create_time_ts",
            "num_threads",
        }

        if key in numeric_sort_keys:
            return sorted(
                process_list,
                key=lambda item: (
                    float(value)
                    if (value := item.get(key)) is not None and isinstance(value, (int, float))
                    else 0.0
                ),
                reverse=reverse,
            )

        return sorted(
            process_list,
            key=lambda item: str(item.get(key)).lower() if item.get(key) is not None else "",
            reverse=reverse,
        )

    def _format_duration_seconds(self, seconds: float) -> str:
        total_seconds = float(seconds)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, secs = divmod(remainder, 60)

        if hours >= 1:
            return f"{int(hours)}h {int(minutes)}m {secs:05.2f}s"
        if minutes >= 1:
            return f"{int(minutes)}m {secs:05.2f}s"
        return f"{secs:.3f}s"
