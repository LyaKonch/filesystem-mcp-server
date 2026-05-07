import logging
from abc import ABC, abstractmethod

import psutil
from fastmcp import Context
from fastmcp.dependencies import Depends

from auth.permissions import guard
from utilities import dependencies
from utilities.decorators import export_tool
from utilities.error_handling import ToolOperationError


class BaseProcessManager(ABC):
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

    @abstractmethod
    def start_process(self, command):
        pass

    @abstractmethod
    def kill_process(self, process_id):
        pass

    @abstractmethod
    def suspend_process(self, process_id):
        pass

    @abstractmethod
    def resume_process(self, process_id):
        pass

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
