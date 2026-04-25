from abc import ABC, abstractmethod

import psutil


class BaseProcessManager(ABC):
    def list_processes(filter_by_name, limit, sort_by):
        pass

    def get_process_info(pid):
        pass

    def get_process_connections(pid):
        pass

    def get_process_tree(pid):
        pass

    def get_process_open_files(pid):
        pass

    @abstractmethod
    def start_process(self, command):
        pass

    @abstractmethod
    def kill_process(self, process_id):
        pass

    @abstractmethod
    def suspend_process(self, process_id):
        pass

    def is_process_running(self, process_id):
        return psutil.pid_exists(process_id)
