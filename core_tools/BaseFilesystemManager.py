import asyncio
import errno
import fnmatch
import logging
import os
import shutil
import sys
from abc import ABC, abstractmethod
from pathlib import Path

import aiofiles
from fastmcp import Context
from fastmcp.dependencies import Depends

from auth.permissions import guard, policy_manager
from utilities.decorators import export_tool
from utilities.dependencies import (
    checkSamplingCapability,
    format_size,
    format_timestamp,
    request_elicitation_permission,
    validate_path,
)
from utilities.error_handling import ToolOperationError
from utilities.filereader import FileReader
from utilities.imagereader import ImageReader


class BaseFilesystemManager(ABC):
    def __init__(self):
        self.module_logger = logging.getLogger(__name__)

    @export_tool(
        name="list_files", logger=logging.getLogger(__name__), tags=["filesystem.list_files"]
    )
    async def list_files(
        self,
        path: str,
        ctx: Context,
        depth: int = 1,
        recursive: bool = False,
        pattern: str = "*",
        exclude_dirs: list[str] | None = None,
        file_type: str = "all",  # "file", "directory", "all"
        calculate_size: bool = False,
        constraints: dict | None = Depends(guard("filesystem.list_files")),
    ) -> dict | str:
        """List files and directories at the given path.
        recursive: whether to recurse into subdirectories
        depth: how deep to recurse into subdirectories (default: 1, max: 10 or as per constraints) - ignored if recursive is False
        pattern is for filtering results by name, for example *.txt or *.log (you dont need to specify **/ for recursive search, it will be searched recursively automatically if recursive=True)
        file_type: "file", "directory", or "all" to filter results
        calculate_size: whether to calculate total size for directories (can be heavy for large directories, use with caution)
        exclude_dirs: list of directory names to exclude from results (e.g. [".git", "node_modules"]). there is default value if you dont provide any, which includes common large directories that are usually not interesting to list. you can set it to empty list [] if you want to include everything. this filter is applied before pattern and type filters.
        """
        constraints = constraints or {}
        try:
            target_path = await validate_path(path, ctx, must_exist=True, expected_type="dir")
            if "allowed_paths" in constraints and not policy_manager.check_constraint(
                constraints, "allowed_paths", target_path
            ):
                raise ToolOperationError(
                    "access_denied",
                    f"Access denied to path: {target_path}",
                    actions=["Check your permissions or contact an administrator."],
                )
            depth_limit = (constraints or {}).get("max_depth", 10)
            effective_depth = min(depth_limit, depth) if recursive else 1
            result = await self._build_tree_recursive(
                target_path,
                max_depth=effective_depth,
                calculate_size=calculate_size,
                pattern=pattern,
                exclude_dirs=exclude_dirs,
                file_type=file_type,
            )
            result = result if result else "No matching files or directories found."
            return result
        except ToolOperationError:
            raise
        except Exception as e:
            raise ToolOperationError(
                "operation_failed",
                f"Failed to list files in '{path}': {e}",
                actions=[
                    "Verify the path points to an accessible directory.",
                    "Check directory permissions.",
                    "Retry the operation.",
                ],
            ) from e

    async def _build_tree_recursive(
        self,
        path: Path,
        max_depth: int,
        calculate_size: bool = False,
        pattern: str = "*",
        exclude_dirs: list[str] | None = None,
        file_type: str = "all",  # "file", "directory", "all"
        current_depth: int = 0,
    ) -> dict | None | str:
        """Recursively build a tree structure of files and directories with depth control."""

        if exclude_dirs is None:
            exclude_dirs = [".git", "node_modules", "__pycache__", ".venv"]

        node = await self._get_item_stats(path, calculate_size=calculate_size)
        is_dir = node.get("type") == "directory"

        if is_dir and current_depth < max_depth:
            node["children"] = []
            try:
                for child in path.iterdir():
                    if exclude_dirs and path.name in exclude_dirs:
                        continue

                    child_node = await self._build_tree_recursive(
                        child,
                        max_depth,
                        calculate_size,
                        pattern,
                        exclude_dirs,
                        file_type,
                        current_depth + 1,
                    )

                    if child_node is not None:
                        node["children"].append(child_node)
            except PermissionError:
                node["children"] = []
                node["error"] = "Access Denied"
            except Exception as e:
                node["error"] = str(e)

        # filtration logic for current node
        matches_type = (file_type == "all") or (
            node.get("type") == file_type
        )  # file or directory or all
        matches_pattern = fnmatch.fnmatch(path.name, pattern)  # pattern matching in name

        # if node passed filters
        if matches_type and matches_pattern:
            return node

        # when node doesn't match filters but has children that match patterns
        if is_dir and node.get("children"):
            return node

        # no filters no useful children
        return None

    # different file types have different properties e.g. metadata
    # for example docx have author number of pages,
    # video can have length width height etc
    # same with audio and pictures
    async def _get_item_stats(self, path: Path, calculate_size: bool = False) -> dict:
        """Get metadata about a file or directory, including size, type, permissions."""
        try:
            stats = path.stat()
            # (Windows: birthtime/ctime, Linux: birthtime/metadata change)
            created = getattr(stats, "st_birthtime", stats.st_ctime)

            is_dir = path.is_dir()
            item_info = {
                "name": path.name if path.name else str(path),
                "type": "directory" if is_dir else "file",
                "modified": format_timestamp(stats.st_mtime),
                "created": format_timestamp(created),
                "permissions": oct(stats.st_mode)[-3:],
                "owner": await self.get_owner(path),
            }
            if is_dir:
                try:
                    entries = list(os.scandir(path))
                    item_info["items_count"] = str(len(entries))
                except PermissionError:
                    item_info["items_count"] = "Permission Denied"
                if calculate_size:
                    # heavy operation
                    size, files, dirs, limited = await asyncio.to_thread(
                        self.get_dir_stats, str(path)
                    )
                    item_info.update(
                        {
                            "size_str": format_size(size),
                            "files": files,
                            "folders": dirs,
                            "stats_is_partial": limited,
                        }
                    )
            if not is_dir:
                item_info["size_str"] = format_size(stats.st_size)
                item_info["extension"] = path.suffix.lower()
            return item_info
        except Exception as e:
            raise ToolOperationError(
                "operation_failed",
                f"Failed to get stats for '{path}': {e}",
                actions=[
                    "Verify the path points to an accessible file or directory.",
                    "Check file/directory permissions.",
                    "Retry the operation.",
                ],
            ) from e

    async def get_owner(self, path: Path) -> str:
        try:
            if sys.platform == "win32":  # Windows
                # easy way using powershell
                cmd = f"(Get-Acl '{path}').Owner"
                process = await asyncio.create_subprocess_exec(
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await process.communicate()
                return stdout.decode("utf-8", errors="ignore").strip()
            else:  # Linux / macOS
                return str(path.owner())
        except Exception:
            return "Unknown"

    # def is_hidden(self, path: Path):
    #     if sys.platform.startswith("win"):
    #         try:
    #             import ctypes
    #             attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
    #             return attrs != -1 and bool(attrs & 2) # 2 - FILE_ATTRIBUTE_HIDDEN
    #         except:
    #             return False
    #     return path.name.startswith(".") # on linux hidden files start with a dot

    def get_dir_stats(self, path: str, max_files: int = 10000):
        """
        Counts total size, number of files and directories within the given directory path.
        max_files — a safety limit
        """
        size = 0
        files = 0
        dirs = 0

        try:
            with os.scandir(path) as it:
                for entry in it:
                    if (files + dirs) > max_files:
                        return size, files, dirs, True  # limit reached

                    try:
                        if entry.is_file(follow_symlinks=False):
                            files += 1
                            size += entry.stat().st_size
                        elif entry.is_dir(follow_symlinks=False):
                            dirs += 1
                            s, f, d, limited = self.get_dir_stats(
                                entry.path, max_files - (files + dirs)
                            )
                            size += s
                            files += f
                            dirs += d
                            if limited:
                                return size, files, dirs, True
                    except (PermissionError, OSError):
                        continue  # just skipping

        except (PermissionError, OSError):
            pass

        return size, files, dirs, False

    @export_tool(
        name="get_path_info", logger=logging.getLogger(__name__), tags=["filesystem.get_path_info"]
    )
    async def get_path_info(
        self,
        path: str,
        ctx: Context,
        depth: int,
        calculate_size: bool = False,
        constraints: dict | None = Depends(guard("filesystem.get_path_info")),
    ) -> dict | str | None:
        """Get detailed metadata about a file or directory.

        Args:
                path: Path to the file or directory
                depth: Maximum depth to traverse. only for directories, ignored for files. Default is 1 (only the item itself).
                calculate_size: Whether to calculate the size of directories
        """
        constraints = constraints or {}
        try:
            target_path = await validate_path(path, ctx, must_exist=True)

            if "allowed_paths" in constraints and not policy_manager.check_constraint(
                constraints, "allowed_paths", target_path
            ):
                raise ToolOperationError(
                    "access_denied",
                    f"Access denied to path: {target_path}",
                    actions=["Check your permissions or contact an administrator."],
                )

            max_depth = (constraints or {}).get("max_depth", 1)

            if "max_depth" in constraints and not policy_manager.check_constraint(
                constraints, "max_depth", depth
            ):
                await ctx.warning(
                    "Provided depth exceeds your allowed max_depth constraint. Using the maximum allowed depth instead."
                )
                max_depth = min(max_depth, depth)

            result = await self._build_tree_recursive(
                target_path, max_depth=max_depth, calculate_size=calculate_size
            )

            return result

        except ToolOperationError:
            raise
        except Exception as e:
            raise ToolOperationError(
                "operation_failed",
                f"Failed to get file info for '{path}': {e}",
                actions=[
                    "Verify the path is accessible.",
                    "Check file permissions.",
                    "Retry the operation.",
                ],
            ) from e

    @export_tool(
        name="read_file", logger=logging.getLogger(__name__), tags=["filesystem.read_file"]
    )
    async def read_file(
        self,
        path: str,
        ctx: Context,
        include_images: bool = False,
        read_from: str = "beginning",  # "beginning" або "end"
        max_bytes: int = 50000,
        constraints: dict | None = Depends(guard("filesystem.read_file")),
    ):
        """
        Read file content.

        Args:
                path: Path to the file to read
                include_images: Whether to include image data in the result (Sample their description)
                BEWARE: Use with caution and only when necessary.
                Its like adding images to the prompt, thus your limit can be reached very fast, especially with files containing many images.
                Also not every client supports sampling and not every model supports OCR/vision, therefore, if you need this tool, you should check those info beforehand.
        """
        constraints = constraints or {}
        try:
            target_path = await validate_path(path, ctx, must_exist=True, expected_type="file")

            if "allowed_paths" in constraints and not policy_manager.check_constraint(
                constraints, "allowed_paths", target_path
            ):
                raise ToolOperationError(
                    "access_denied",
                    f"Access denied to path: {target_path}",
                    actions=["Check your permissions or contact an administrator."],
                )

            file_size = target_path.stat().st_size  # in bytes

            if "max_read_size" in constraints and not policy_manager.check_constraint(
                constraints, "max_read_size", file_size
            ):
                raise ToolOperationError(
                    "access_denied",
                    f"File '{path}' exceeds the maximum allowed size.",
                    actions=["Choose a smaller file or contact an administrator."],
                )

            reader = None
            if include_images:
                if checkSamplingCapability(ctx.session):
                    reader = ImageReader()
                else:
                    await ctx.info(
                        "Client does not support sampling, cannot include image descriptions."
                    )
                    include_images = False

            result = await FileReader(
                [target_path],
                include_images=include_images,
                read_from=read_from,
                max_bytes=max_bytes,
            ).read()

            if result and len(result) > 0:
                file_data = result[0]
                file_content = file_data.get("content", {})

                # for docx files, file_content has "pages" key with list of page dicts
                if isinstance(file_content, dict) and "pages" in file_content:
                    pages = file_content["pages"]

                    # If include_images and reader is available, describe images
                    if include_images and reader:
                        for page in pages:
                            for obj in page.get("media", []):
                                if obj["kind"] == "image":
                                    try:
                                        image_b64 = obj["data"].get("bytes_b64", "")
                                        mime_type = obj["data"].get("mime_type", "image/png")
                                        if image_b64:
                                            description = await reader.describe_base64(
                                                image_b64, ctx, mime_type
                                            )
                                            obj["description"] = description
                                        obj["data"].pop("bytes_b64", None)
                                        obj["data"].pop("sha1", None)
                                    except Exception as e:
                                        self.module_logger.warning(
                                            "Failed to describe image %s: %s", obj["id"], e
                                        )

                return file_data

            return {"metadata": {}, "content": {}}

        except UnicodeDecodeError as e:
            raise ToolOperationError(
                "validation",
                f"File '{path}' contains binary data or unsupported encoding",
                actions=[
                    "Use a text-based file.",
                    "Try a different file encoding.",
                    "Retry without image description if applicable.",
                ],
            ) from e
        except ToolOperationError:
            raise
        except Exception as e:
            raise ToolOperationError(
                "operation_failed",
                f"Failed to read file '{path}': {e}",
                actions=[
                    "Verify the file exists and is readable.",
                    "Check file permissions.",
                    "Retry the operation.",
                ],
            ) from e

    @export_tool(
        name="write_file",
        logger=logging.getLogger(__name__),
        tags=["filesystem.write_file"],
    )
    async def write_file(
        self,
        path: str,
        content: str,
        ctx: Context,
        mode: str = "overwrite",  # "overwrite" або "append"
        constraints: dict | None = Depends(guard("filesystem.write_file")),
    ) -> dict | str:
        """
        Create a new file, overwrite an existing one, or append content to it.

        Args:
            path: Destination file path.
            content: Text content to write.
            mode: 'overwrite' (replaces entire file) or 'append' (adds to the end).
        """
        constraints = constraints or {}

        try:
            target_path = await validate_path(path, ctx, must_exist=False)

            if target_path.exists() and target_path.is_dir():
                raise ToolOperationError(
                    "validation",
                    f"Cannot write to '{path}' because it is a directory.",
                    actions=["Specify a file path, not a directory."],
                )

            if "allowed_paths" in constraints and not policy_manager.check_constraint(
                constraints, "allowed_paths", target_path
            ):
                raise ToolOperationError(
                    "access_denied",
                    f"Access denied to write to path: {target_path}",
                    actions=["Check your permissions or contact an administrator."],
                )

            # bytes in utf-8 encoding
            content_bytes = content.encode("utf-8")
            content_size = len(content_bytes)
            max_write_size = constraints.get("max_write_size", 5 * 1024 * 1024)  # default 5 MB

            if "max_write_size" in constraints and not policy_manager.check_constraint(
                constraints, "max_write_size", max_write_size
            ):
                raise ToolOperationError(
                    "limit_exceeded",
                    f"Content size ({content_size} bytes) exceeds the maximum allowed write size ({max_write_size} bytes).",
                    actions=[
                        "Write smaller chunks or request an administrator to increase your limit."
                    ],
                )

            # creating parent directories if they don't exist
            try:
                target_path.parent.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                raise ToolOperationError(
                    "operation_failed", f"Failed to create parent directories for '{path}': {e}"
                ) from e

            if mode == "append":
                async with aiofiles.open(str(target_path), "a", encoding="utf-8") as f:
                    await f.write(content)
            else:
                async with aiofiles.open(str(target_path), "w", encoding="utf-8") as f:
                    await f.write(content)

            return {
                "status": "success",
                "action": "appended" if mode == "append" else "created_or_overwritten",
                "path": str(target_path),
                "bytes_written": content_size,
            }

        except ToolOperationError:
            raise
        except Exception as e:
            raise ToolOperationError(
                "operation_failed",
                f"Failed to write file '{path}': {e}",
                actions=[
                    "Verify the path is writable.",
                    "Check disk space and permissions.",
                    "Retry the operation.",
                ],
            ) from e

    @export_tool(
        name="edit_file",
        logger=logging.getLogger(__name__),
        tags=["filesystem.edit_file"],
    )
    async def edit_file(
        self,
        path: str,
        old_text: str,
        new_text: str,
        ctx: Context,
        replace_all: bool = False,
        constraints: dict | None = Depends(guard("filesystem.edit_file")),
    ) -> dict | str:
        """
        Edit a file by finding a specific text block and replacing it.
        This is the preferred way to modify files safely without rewriting the entire file.

        Args:
            path: Path to the file.
            old_text: The EXACT text block currently in the file that you want to replace.
                      MUST match perfectly, including spaces, tabs, and newlines.
            new_text: The new text block to insert in place of old_text.
            replace_all: If True, replaces all occurrences. If False (default), replaces only the first occurrence.
        """
        constraints = constraints or {}

        try:
            target_path = await validate_path(path, ctx, must_exist=True, expected_type="file")

            if "allowed_paths" in constraints and not policy_manager.check_constraint(
                constraints, "allowed_paths", target_path
            ):
                raise ToolOperationError(
                    "access_denied",
                    f"Access denied to edit path: {target_path}",
                    actions=["Check your permissions or contact an administrator."],
                )

            file_size = target_path.stat().st_size
            max_read_size = constraints.get("max_read_size", 10 * 1024 * 1024)  # Дефолт 10 МБ
            if "max_read_size" in constraints and not policy_manager.check_constraint(
                constraints, "max_read_size", file_size
            ):
                raise ToolOperationError(
                    "limit_exceeded",
                    f"File is too large to edit ({format_size(file_size)}). Limit is {format_size(max_read_size)}.",
                    actions=["Ask admin to increase limit or use terminal tools for huge files."],
                )

            try:
                async with aiofiles.open(str(target_path), encoding="utf-8") as f:
                    content = await f.read()
            except UnicodeDecodeError as e:
                raise ToolOperationError(
                    "validation",
                    f"File '{path}' appears to be binary or not UTF-8 encoded. Cannot edit text.",
                    actions=["Ensure the file is a text file."],
                ) from e

            occurrences = content.count(old_text)
            if occurrences == 0:
                raise ToolOperationError(
                    "not_found",
                    "The exact 'old_text' was not found in the file.",
                    actions=[
                        "Ensure you copied the text exactly as it appears in the file.",
                        "Check for hidden whitespace, tabs, or different line endings (\\n vs \\r\\n).",
                        "Use read_file first to get the exact block you want to replace.",
                    ],
                )

            replace_count = -1 if replace_all else 1
            new_content = content.replace(old_text, new_text, replace_count)

            async with aiofiles.open(str(target_path), "w", encoding="utf-8") as f:
                await f.write(new_content)

            return {
                "status": "success",
                "path": str(target_path),
                "occurrences_found": occurrences,
                "replacements_made": occurrences if replace_all else 1,
                "message": "File successfully edited.",
            }

        except ToolOperationError:
            raise
        except Exception as e:
            raise ToolOperationError(
                "operation_failed",
                f"Failed to edit file '{path}': {e}",
                actions=["Check permissions and file locks."],
            ) from e

    @export_tool(
        name="create_directory",
        logger=logging.getLogger(__name__),
        tags=["filesystem.create_directory"],
    )
    async def create_directory(
        self,
        path: str,
        ctx: Context,
        constraints: dict | None = Depends(guard("filesystem.create_directory")),
    ) -> dict | str:
        """Create a new directory."""
        constraints = constraints or {}
        try:
            target_path = await validate_path(path, ctx, must_exist=False)

            if "allowed_paths" in constraints and not policy_manager.check_constraint(
                constraints, "allowed_paths", target_path
            ):
                raise ToolOperationError(
                    "access_denied",
                    f"Access denied to create directory: {target_path}",
                    actions=["Check your permissions or contact an administrator."],
                )

            if target_path.exists():
                if target_path.is_dir():
                    return {
                        "status": "success",
                        "message": "Directory already exists",
                        "path": str(target_path),
                    }
                else:
                    raise ToolOperationError(
                        "validation",
                        f"A file with the same name already exists at '{path}'",
                        actions=[
                            "Choose a different directory name or delete/rename the existing file first."
                        ],
                    )

            target_path.mkdir(parents=True, exist_ok=True)
            return {
                "status": "success",
                "message": "Directory created successfully",
                "path": str(target_path),
            }
        except ToolOperationError:
            raise
        except Exception as e:
            raise ToolOperationError(
                "operation_failed",
                f"Failed to create directory '{path}': {e}",
                actions=[
                    "Verify the parent directory is writable.",
                    "Check disk space and permissions.",
                    "Retry the operation.",
                ],
            ) from e

    @export_tool(
        name="move_file", logger=logging.getLogger(__name__), tags=["filesystem.move_file"]
    )
    async def move_file(
        self,
        source: str,
        destination: str,
        ctx: Context,
        constraints: dict | None = Depends(guard("filesystem.move_file")),
    ) -> dict | str:
        """Move or rename files and directories.

        Args:
                source: Source path
                destination: Destination path
        """
        constraints = constraints or {}
        try:
            source_path = await validate_path(source, ctx, must_exist=True)
            dest_path = await validate_path(destination, ctx, must_exist=False)

            if "allowed_paths" in constraints:
                if not policy_manager.check_constraint(constraints, "allowed_paths", source_path):
                    raise ToolOperationError(
                        "access_denied", f"Access denied to source: {source_path}"
                    )
                if not policy_manager.check_constraint(constraints, "allowed_paths", dest_path):
                    raise ToolOperationError(
                        "access_denied", f"Access denied to destination: {dest_path}"
                    )

            if dest_path.exists():
                raise ToolOperationError(
                    "validation",
                    f"Destination '{destination}' already exists",
                    actions=[
                        "Choose a different destination path.",
                        "Delete or rename the existing target first.",
                        "Retry with a unique destination.",
                    ],
                )

            try:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                raise ToolOperationError(
                    "operation_failed",
                    f"Failed to create parent directories for destination: {e}",
                    actions=[
                        "Verify the parent directory is writable.",
                        "Check disk space and permissions.",
                        "Retry the operation.",
                    ],
                ) from e

            await asyncio.to_thread(shutil.move, str(source_path), str(dest_path))

            return {
                "status": "success",
                "message": "Moved successfully",
                "source": str(source_path),
                "destination": str(dest_path),
            }

        except ToolOperationError:
            raise
        except Exception as e:
            raise ToolOperationError(
                "operation_failed",
                f"Failed to move from '{source}' to '{destination}': {e}",
                actions=[
                    "Verify source and destination paths.",
                    "Check file and directory permissions.",
                    "Ensure the file is not locked by another process.",
                ],
            ) from e

    @export_tool(
        name="search_files", logger=logging.getLogger(__name__), tags=["filesystem.search_files"]
    )
    async def search_files(
        self,
        path: str,
        query: str,
        ctx: Context,
        constraints: dict | None = Depends(guard("filesystem.search_files")),
    ) -> str | dict:
        """
        Search for a specific text query inside all files within a directory.
        Uses fast system utilities (grep/findstr) under the hood.

        Args:
            path: The directory to search in.
            query: The exact text string to search for.
        """
        constraints = constraints or {}
        try:
            target_path = await validate_path(path, ctx, must_exist=True, expected_type="dir")

            if "allowed_paths" in constraints and not policy_manager.check_constraint(
                constraints, "allowed_paths", target_path
            ):
                raise ToolOperationError(
                    "access_denied", f"Access denied to search in: {target_path}"
                )

            # platform dependent call (implemented in Windows/Linux classes)
            results = await self._search_content(target_path, query)

            return {
                "status": "success",
                "path": str(target_path),
                "query": query,
                "matches_found": len(results),
                "results": results,
            }

        except ToolOperationError:
            raise
        except Exception as e:
            raise ToolOperationError(
                "operation_failed",
                f"Failed to search files in '{path}': {e}",
                actions=[
                    "Verify the search path is accessible.",
                    "Check the search pattern.",
                    "Retry the operation.",
                ],
            ) from e

    @abstractmethod
    async def _search_content(self, target_path: Path, query: str) -> list[dict]:
        """Executes OS-specific search command and parses the output."""
        pass

    @export_tool(
        name="delete_path",
        logger=logging.getLogger(__name__),
        tags=["filesystem.delete_path"],
    )
    async def delete_path(
        self,
        path: str,
        ctx: Context,
        recursive: bool = False,
        constraints: dict | None = Depends(guard("filesystem.delete_path")),
    ) -> dict | str:
        """
        Delete a file or an empty directory.
        If deleting a directory that contains files, you MUST set recursive=True.
        """
        constraints = constraints or {}
        try:
            target_path = await validate_path(path, ctx, must_exist=True)

            if "allowed_paths" in constraints and not policy_manager.check_constraint(
                constraints, "allowed_paths", target_path
            ):
                raise ToolOperationError(
                    "access_denied",
                    f"Access denied to delete: {target_path}",
                    actions=["Check your permissions or contact an administrator."],
                )

            is_dir = target_path.is_dir()

            item_type = (
                "directory AND ALL ITS CONTENTS"
                if (is_dir and recursive)
                else ("directory" if is_dir else "file")
            )
            reason = (
                f"Are you sure you want to permanently delete the {item_type} at '{target_path}'?"
            )

            permission = await request_elicitation_permission(ctx, reason)

            if permission is False:
                self.module_logger.info(f"User declined to delete {target_path}.")
                return {
                    "status": "cancelled",
                    "message": f"Deletion of {target_path} cancelled by user.",
                }

            if permission is None:
                self.module_logger.warning(
                    f"Proceeding with deletion of {target_path} without UI confirmation (unsupported by client)."
                )

            try:
                if is_dir:
                    if recursive:
                        # not blocking server while deleting large directories
                        await asyncio.to_thread(shutil.rmtree, target_path)
                    else:
                        target_path.rmdir()  # raise error if directory is not empty
                else:
                    target_path.unlink()  # file deletion

            except OSError as e:
                # checking if error is due to directory not being empty
                if e.errno == errno.ENOTEMPTY or e.errno == 145 or "not empty" in str(e).lower():
                    raise ToolOperationError(
                        "validation",
                        "Directory is not empty. Set recursive=True to delete it and all its contents.",
                        actions=["Retry with recursive=True"],
                    ) from e
                raise  # If this is another error (e.g., PermissionError), raise it further

            return {
                "status": "success",
                "message": f"{'Directory' if is_dir else 'File'} deleted successfully",
                "path": str(target_path),
            }

        except ToolOperationError:
            raise
        except Exception as e:
            raise ToolOperationError(
                "operation_failed",
                f"Failed to delete '{path}': {e}",
                actions=[
                    "Check if the file is locked by another process or if you have enough permissions."
                ],
            ) from e
