from __future__ import annotations

from typing import TYPE_CHECKING

from core_tools.OSManager import BaseOSManager

if TYPE_CHECKING:
    pass


class LinuxOSManager(BaseOSManager):
    def __init__(self, process_mgr, service_mgr, fs_mgr, system_mgr):
        super().__init__(process_mgr, service_mgr, fs_mgr, system_mgr)
