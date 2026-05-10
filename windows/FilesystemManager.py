import asyncio
import logging
from pathlib import Path

from core_tools.BaseFilesystemManager import BaseFilesystemManager


class FilesystemManager(BaseFilesystemManager):
    def __init__(self):
        # self.os_manager = os_manager
        self.logger = logging.getLogger(__name__)

    async def _search_content(self, target_path: Path, query: str) -> list[dict]:
        # path for search, we add  \*
        search_path = str(target_path / "*")

        # PowerShell command, which searches as text, understands UTF-8 and outputs in the format Path:Line:Content
        # -SimpleMatch means we look for an exact match, not a regular expression (safe for special characters)
        ps_command = (
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
            f"Select-String -Path '{search_path}' -Pattern '{query}' -SimpleMatch -Encoding utf8 "
            "| ForEach-Object { $_.Path + ':' + $_.LineNumber + ':' + $_.Line }"
        )

        cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_command]

        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if stderr:
            self.logger.warning(
                f"PowerShell search errors: {stderr.decode('cp1251', errors='ignore')}"
            )

        results: list[dict] = []
        if not stdout:
            return results

        # Decode the output
        # PowerShell may return utf-8 or cp866 depending on the system, errors="replace" saves from crashing
        output_lines = stdout.decode("utf-8", errors="replace").strip().split("\n")

        for line in output_lines:
            try:
                # Parse the format C:\path\file.txt:10:text
                first_colon_idx = line.index(":", 2)
                second_colon_idx = line.index(":", first_colon_idx + 1)

                file_path = line[:first_colon_idx]
                line_num = line[first_colon_idx + 1 : second_colon_idx]
                content = line[second_colon_idx + 1 :]

                results.append({"file": file_path, "line": line_num, "content": content.strip()})
            except ValueError:
                continue

        return results
