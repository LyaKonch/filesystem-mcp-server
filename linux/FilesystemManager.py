import asyncio
import logging
from pathlib import Path

from core_tools.BaseFilesystemManager import BaseFilesystemManager


class FilesystemManager(BaseFilesystemManager):
    def __init__(self):
        # self.os_manager = os_manager
        self.logger = logging.getLogger(__name__)

    async def _search_content(self, target_path: Path, query: str) -> list[dict]:
        # command: grep -rnI "query" /path/to/dir
        cmd = ["grep", "-rnI", query, str(target_path)]

        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        stdout, _ = await process.communicate()

        results = []
        if not stdout:
            return results

        # grep outputs in the format: /path/to/file.txt:42:matching text
        output_lines = stdout.decode("utf-8", errors="ignore").strip().split("\n")

        for line in output_lines:
            # Split into a maximum of 3 parts (path, line, content)
            parts = line.split(":", 2)
            if len(parts) == 3:
                file_path, line_num, content = parts
                results.append({"file": file_path, "line": line_num, "content": content.strip()})

        return results
