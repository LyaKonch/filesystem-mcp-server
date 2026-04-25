import logging

from core_tools.BaseServiceManager import BaseServiceManager


class ServiceManager(BaseServiceManager):
    def __init__(self):
        # self.os_manager = os_manager
        self.logger = logging.getLogger(__name__)
