import logging

from core_tools.BaseProcessManager import BaseProcessManager


class ProcessManager(BaseProcessManager):
    def __init__(self):
        # self.os_manager = os_manager
        self.logger = logging.getLogger(__name__)

    def _get_subprocess_kwargs(self, use_shell: bool) -> dict:
        return {"start_new_session": True}

    def start_process(self, command):
        pass

    def kill_process(self, process_id):
        pass

    def suspend_process(self, process_id):
        pass

    def resume_process(self, process_id):
        pass
