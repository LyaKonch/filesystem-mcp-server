import logging

from core_tools.BaseFilesystemManager import BaseFilesystemManager


class FilesystemManager(BaseFilesystemManager):
    def __init__(self):
        # self.os_manager = os_manager
        self.logger = logging.getLogger(__name__)
