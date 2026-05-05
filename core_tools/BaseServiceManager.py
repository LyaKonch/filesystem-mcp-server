from abc import ABC, abstractmethod

from fastmcp import Context


class BaseServiceManager(ABC):
    @abstractmethod
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
        pass

    @abstractmethod
    async def get_service_status(self, service_name: str) -> dict:
        """Get detailed status for a specific service."""
        pass

    @abstractmethod
    async def start_service(self, service_name: str, args: list | None = None) -> str:
        """Start a stopped service."""
        pass

    @abstractmethod
    async def stop_service(self, service_name: str) -> str:
        """Stop a running service."""
        pass

    @abstractmethod
    async def stop_service_with_deps(self, service_name: str) -> str:
        """Stop a service and its dependencies."""
        pass

    @abstractmethod
    async def restart_service(self, service_name: str) -> str:
        """Restart a running service."""
        pass

    @abstractmethod
    async def change_service_startup_type(self, service_name: str, startup_type: str) -> str:
        """Change service startup type (automatic, manual, disabled)."""
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    async def get_service_logs(
        self, service_name: str, source_name: str | None = None, max_records: int = 50
    ) -> list:
        """Get service logs if available."""
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    async def delete_service(self, ctx: Context, service_name: str) -> str:
        """Delete an existing service (requires confirmation)."""
        pass

    @abstractmethod
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
        pass
