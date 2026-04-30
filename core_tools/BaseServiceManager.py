from abc import ABC, abstractmethod


class BaseServiceManager(ABC):
    @abstractmethod
    def get_services():
        pass

    @abstractmethod
    def get_service_status():
        pass

    @abstractmethod
    def start_service():
        "Start stopped service"
        pass

    @abstractmethod
    def stop_service():
        "Stop running service"
        pass

    @abstractmethod
    def restart_service():
        "Restart running service"
        pass

    @abstractmethod
    def change_service_startup_type():
        "Change service startup type (automatic, manual, disabled)"
        pass

    @abstractmethod
    def change_service_config():
        "Change service configuration such as executable path, arguments, environment variables, etc."
        pass

    @abstractmethod
    def get_service_logs():
        "Get service logs if available (may be limited to certain services or require additional configuration)"
        pass

    @abstractmethod
    def create_service():
        "Create new service with specified configuration (executable path, arguments, environment variables, startup type, etc.)"
        pass

    @abstractmethod
    def delete_service():
        "Delete existing service (may require stopping it first)"
        pass
