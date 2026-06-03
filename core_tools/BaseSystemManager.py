import os
from abc import ABC, abstractmethod
from enum import Enum

from fastmcp import Context


class EnvScope(Enum):
    PROCESS = "process"  # for current session, this process and its children (os.environ)
    USER = "user"  # for the current user (stored permanently, e.g. in Windows Registry or Linux ~/.bashrc)
    SYSTEM = "system"  # for all users on the system (requires admin rights, stored permanently). to see changes in current session, user needs restart)


class BaseSystemManager(ABC):
    # @abstractmethod
    # def restart_system(self) -> str:
    #    pass

    @abstractmethod
    def get_variable(self, name: str, scope: EnvScope = EnvScope.USER) -> str | None:
        pass

    @abstractmethod
    def list_variables(self, scope: EnvScope = EnvScope.USER) -> dict[str, str]:
        pass

    @abstractmethod
    async def set_variable(
        self, name: str, value: str, scope: EnvScope = EnvScope.USER, ctx: Context | None = None
    ) -> str:
        """Set an environment variable. Implementations may optionally accept `ctx`.

        The `ctx` argument is optional and placed at the end to keep helper
        methods (which call `set_variable` without a ctx) ergonomic.
        """
        raise NotImplementedError()

    @abstractmethod
    async def delete_variable(
        self, name: str, scope: EnvScope = EnvScope.USER, ctx: Context | None = None
    ) -> str:
        """Delete an environment variable. Implementations may optionally accept `ctx`.

        The `ctx` argument is optional and placed at the end to keep helper
        methods (which call `delete_variable` without a ctx) ergonomic.
        """
        raise NotImplementedError()

    # @abstractmethod
    # async def get_hardware_info(self, ctx:Context, name: str) -> str:
    #     pass

    # @abstractmethod
    # async def get_sensors_info(self, ctx:Context, name: str) -> str:
    #     pass
    # ==========================================
    # 3. SAFE PATH MANAGEMENT
    # ==========================================

    async def append_to_variable(
        self, name: str, value: str, scope: EnvScope = EnvScope.USER
    ) -> str:
        """Mostly useful for PATH-like variables. Appends a value to a separator-delimited list if it's not already present."""
        try:
            current_value = self.get_variable(name, scope)
        except Exception as e:
            return f"Failed to get current value of variable: {str(e)}"
        if not current_value:
            return f"Variable {name} is empty or not found"
        separator = os.pathsep  # automatically either ';' or ':'

        if current_value:
            paths = current_value.split(separator)
            if value in paths:
                return f"Value '{value}' already exists in {name}"
            new_value = current_value + separator + value
        else:
            new_value = value

        return await self.set_variable(name, new_value, scope)

    async def remove_from_variable(
        self, name: str, value: str, scope: EnvScope = EnvScope.USER
    ) -> str:
        """Mostly useful for PATH-like variables. Removes a value from a separator-delimited list if it exists."""
        try:
            current_value = self.get_variable(name, scope)
        except Exception as e:
            return f"Failed to get current value of variable: {str(e)}"
        if not current_value:
            return f"Variable {name} is empty or not found"

        separator = os.pathsep  # automatically either ';' or ':'
        paths = current_value.split(separator)

        if value not in paths:
            return f"Value '{value}' not found in {name}"

        paths.remove(value)
        new_value = separator.join(paths)

        if not new_value:
            return await self.delete_variable(name, scope)
        return await self.set_variable(name, new_value, scope)

    def _validate_key_name(self, name: str):
        if "=" in name or " " in name:
            raise ValueError(f"Invalid name: '{name}'. No spaces or '=' allowed.")
        if not name:
            raise ValueError("Name cannot be empty.")
