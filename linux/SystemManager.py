import logging

from core_tools.BaseSystemManager import BaseSystemManager


class SystemManager(BaseSystemManager):
    def __init__(self):
        self.logger = logging.getLogger(__name__)
