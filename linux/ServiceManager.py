import logging

from fastmcp import Context

from core_tools.BaseServiceManager import BaseServiceManager


class ServiceManager(BaseServiceManager):
    def __init__(self):
        # self.os_manager = os_manager
        self.logger = logging.getLogger(__name__)

    async def list_services(
        self,
        name: str | None = None,
        status: str | None = None,
        pid: int | None = None,
        username: str | None = None,
        start_type: str | None = None,
        binpath: str | None = None,
        description: str | None = None,
    ) -> list[dict]:
        """List services with optional filtering."""
        raise NotImplementedError()

    async def get_service_status(self, service_name: str) -> dict:
        """Get detailed status for a specific service."""
        raise NotImplementedError()

    async def start_service(self, service_name: str, args: list | None = None) -> str:
        """Start a stopped service."""
        raise NotImplementedError()

    async def stop_service(self, service_name: str) -> str:
        """Stop a running service."""
        raise NotImplementedError()

    async def stop_service_with_deps(self, service_name: str) -> str:
        """Stop a service and its dependencies."""
        raise NotImplementedError()

    async def restart_service(self, service_name: str) -> str:
        """Restart a running service."""
        raise NotImplementedError()

    async def change_service_startup_type(self, service_name: str, startup_type: str) -> str:
        """Change service startup type (automatic, manual, disabled)."""
        raise NotImplementedError()

    async def change_service_config(
        self,
        service_name: str,
        binary_path: str | None = None,
        display_name: str | None = None,
        start_type: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> str:
        """Change service configuration."""
        raise NotImplementedError()

    async def get_service_logs(
        self, service_name: str, source_name: str | None = None, max_records: int = 50
    ) -> list:
        """Get service logs if available."""
        raise NotImplementedError()

    async def create_service(
        self,
        ctx: Context,
        service_name: str,
        display_name: str,
        binary_path: str,
        start_type: str = "manual",
        username: str | None = None,
        password: str | None = None,
    ) -> str:
        """Create a new service with specified configuration (requires confirmation)."""
        raise NotImplementedError()

    async def delete_service(self, ctx: Context, service_name: str) -> str:
        """Delete an existing service (requires confirmation)."""
        raise NotImplementedError()

    async def wrap_script_as_service(
        self,
        ctx: Context,
        service_name: str,
        executor_path: str,
        script_path: str,
        display_name: str | None = None,
        start_type: str = "Automatic",
        stdout_path: str | None = None,
        stderr_path: str | None = None,
    ) -> str:
        """Wrap any script as a background service."""
        raise NotImplementedError()
