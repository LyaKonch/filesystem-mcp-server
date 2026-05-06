import logging
import winreg
from typing import Any

from fastmcp import Context

from auth.permissions import guard
from utilities.decorators import export_tool
from utilities.dependencies import request_elicitation_permission
from utilities.error_handling import ToolOperationError


class RegistryManager:
    hives = {
        "HKEY_CLASSES_ROOT": winreg.HKEY_CLASSES_ROOT,
        "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER,
        "HKEY_LOCAL_MACHINE": winreg.HKEY_LOCAL_MACHINE,
        "HKEY_USERS": winreg.HKEY_USERS,
        "HKEY_CURRENT_CONFIG": winreg.HKEY_CURRENT_CONFIG,
    }

    REG_TYPE_VALUES = [
        winreg.REG_BINARY,
        winreg.REG_DWORD,
        winreg.REG_DWORD_LITTLE_ENDIAN,
        winreg.REG_DWORD_BIG_ENDIAN,
        winreg.REG_EXPAND_SZ,
        winreg.REG_LINK,
        winreg.REG_MULTI_SZ,
        winreg.REG_NONE,
        winreg.REG_QWORD,
        winreg.REG_QWORD_LITTLE_ENDIAN,
        winreg.REG_RESOURCE_LIST,
        winreg.REG_FULL_RESOURCE_DESCRIPTOR,
        winreg.REG_RESOURCE_REQUIREMENTS_LIST,
        winreg.REG_SZ,
    ]
    REG_TYPE_DESCRIPTIONS = {
        winreg.REG_BINARY: "Binary data in any form.",
        winreg.REG_DWORD: "32-bit number.",
        winreg.REG_DWORD_LITTLE_ENDIAN: "32-bit number (little-endian, equivalent to REG_DWORD).",
        winreg.REG_DWORD_BIG_ENDIAN: "32-bit number (big-endian).",
        winreg.REG_EXPAND_SZ: "Null-terminated string containing references to environment variables (e.g. %PATH%).",
        winreg.REG_LINK: "Unicode symbolic link.",
        winreg.REG_MULTI_SZ: "Sequence of null-terminated strings (terminated by two null characters).",
        winreg.REG_NONE: "No defined value type.",
        winreg.REG_QWORD: "64-bit number (added in Python 3.6).",
        winreg.REG_QWORD_LITTLE_ENDIAN: "64-bit little-endian number (equivalent to REG_QWORD, added in Python 3.6).",
        winreg.REG_RESOURCE_LIST: "Device-driver resource list.",
        winreg.REG_FULL_RESOURCE_DESCRIPTOR: "Hardware setting (full resource descriptor).",
        winreg.REG_RESOURCE_REQUIREMENTS_LIST: "Hardware resource requirements list.",
        winreg.REG_SZ: "Null-terminated string.",
    }

    def __init__(self):
        # self.os_manager = os_manager
        self.logger = logging.getLogger(__name__)

    @guard("registry.list_registry_key")
    @export_tool(
        name="list_registry_key",
        logger=logging.getLogger(__name__),
        tags=["registry.list_registry_key"],
    )
    def list_registry_key(
        self, ctx: Context, hive_name: str, sub_key: str, constraints: dict | None = None
    ) -> dict:
        """
        Returns the subkeys and values of a specified registry key.
        hive_name: 'HKEY_CURRENT_USER', 'HKEY_LOCAL_MACHINE', 'HKEY_CLASSES_ROOT', 'HKEY_USERS', 'HKEY_CURRENT_CONFIG'
        sub_key: e.g. 'Environment' under HKEY_CURRENT_USER for user variables or r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment' under HKEY_LOCAL_MACHINE for system variables
        """

        hive = self.hives.get(hive_name.upper())
        if not hive:
            raise ToolOperationError(
                "validation",
                f"Invalid hive: {hive_name}",
                actions=[
                    "Use one of: HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE, HKEY_CLASSES_ROOT, HKEY_USERS, HKEY_CURRENT_CONFIG.",
                    "Retry with a valid hive name.",
                ],
            )

        result: dict[str, Any] = {"sub_keys": [], "values": {}}

        try:
            # with access to read 64-bit registry from a 32-bit process, we need to specify KEY_WOW64_64KEY
            access = winreg.KEY_READ | winreg.KEY_WOW64_64KEY
            with winreg.OpenKey(hive, sub_key, 0, access) as key:
                # subkeys or subfolders
                try:
                    i = 0
                    while True:
                        result["sub_keys"].append(winreg.EnumKey(key, i))
                        i += 1
                except OSError:
                    pass  # OSError means subfolders are finished

                # Read values
                try:
                    i = 0
                    while True:
                        name, value, data_type = winreg.EnumValue(key, i)
                        safe_name = name if name else "(Default)"
                        result["values"][safe_name] = {
                            "value": value,
                            "type": self.REG_TYPE_DESCRIPTIONS.get(data_type, data_type),
                        }
                        i += 1
                except OSError:
                    pass  # no more values

            return result
        except FileNotFoundError as e:
            raise ToolOperationError(
                "not_found",
                f"Registry key not found: {hive_name}\\{sub_key}",
                actions=[
                    "Verify the hive and sub_key names.",
                    "Use list_registry_key with parent keys to explore the structure.",
                ],
            ) from e
        except PermissionError as e:
            raise ToolOperationError(
                "access_denied",
                f"Access denied. Cannot read registry key {hive_name}\\{sub_key}. Administrator privileges may be required.",
                actions=[
                    "Run the server with elevated privileges.",
                    "Use 'Run as Administrator' or equivalent.",
                ],
            ) from e

    @guard("registry.read_registry_key")
    @export_tool(
        name="read_registry_key",
        logger=logging.getLogger(__name__),
        tags=["registry.read_registry_key"],
    )
    def read_registry_key(
        self, ctx: Context, hive_name: str, sub_key: str, name: str, constraints: dict | None = None
    ) -> dict | str:
        """
        Reads a specific value from the Windows registry.
        """
        hive = self.hives.get(hive_name.upper())
        if not hive:
            raise ToolOperationError(
                "validation",
                f"Invalid hive: {hive_name}",
                actions=[
                    "Use one of: HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE, HKEY_CLASSES_ROOT, HKEY_USERS, HKEY_CURRENT_CONFIG.",
                    "Retry with a valid hive name.",
                ],
            )
        try:
            with winreg.OpenKey(hive, sub_key, 0, winreg.KEY_QUERY_VALUE) as key:
                value, data_type = winreg.QueryValueEx(key, name)
                type_description = self.REG_TYPE_DESCRIPTIONS.get(data_type, data_type)
                return dict(value=value, type=type_description)
        except FileNotFoundError as e:
            raise ToolOperationError(
                "not_found",
                f"Registry value not found: {name} in {hive_name}\\{sub_key}",
                actions=[
                    "Verify the value name and key path.",
                    "Use list_registry_key to see available values.",
                ],
            ) from e
        except PermissionError as e:
            raise ToolOperationError(
                "access_denied",
                f"Access denied reading registry value '{name}' from {hive_name}\\{sub_key}.",
                actions=[
                    "Run the server with elevated privileges.",
                    "Use 'Run as Administrator' or equivalent.",
                ],
            ) from e
        except Exception as e:
            raise ToolOperationError(
                "unexpected",
                f"Error reading registry key {hive_name}\\{sub_key}: {str(e)}",
                actions=[
                    "Verify the hive and key path.",
                    "Retry the request.",
                ],
            ) from e

    @guard("registry.write_registry_key")
    @export_tool(
        name="write_registry_key",
        logger=logging.getLogger(__name__),
        tags=["registry.write_registry_key"],
    )
    async def write_registry_key(
        self,
        ctx: Context,
        hive_name: str,
        sub_key: str,
        value_name: str,
        value: str,
        value_type: int,
        constraints: dict | None = None,
    ) -> str:
        """Writes a value to the Windows registry. Scope determines where the value is written (user or system)."""
        hive = self.hives.get(hive_name.upper())
        if not hive:
            raise ToolOperationError(
                "validation",
                f"Invalid hive: {hive_name}",
                actions=[
                    "Use one of: HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE, HKEY_CLASSES_ROOT, HKEY_USERS, HKEY_CURRENT_CONFIG.",
                    "Retry with a valid hive name.",
                ],
            )

        if value_type not in self.REG_TYPE_VALUES:
            raise ToolOperationError(
                "validation",
                f"Invalid registry value type: {value_type}",
                actions=[
                    "Use get_registry_value_types to see valid types.",
                    "Retry with a valid value type.",
                ],
            )

        permission = await request_elicitation_permission(
            ctx,
            f"Are you sure you want to write this registry value in {hive_name}\\{sub_key} "
            f"with name '{value_name}' and value '{value}'? "
            f"If the key does not exist, it will be created. Please confirm.",
        )

        if permission is None:
            raise ToolOperationError(
                "auth_required",
                "Cannot write to registry due to lack of elicitation capability.",
                actions=[
                    "Ensure elicitation is enabled in the server configuration.",
                    "Retry the request.",
                ],
            )
        if permission is False:
            self.logger.info(f"User declined to write to {hive_name}\\{sub_key}")
            return "Operation cancelled by user."

        try:
            with winreg.CreateKeyEx(
                hive, sub_key, 0, winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY
            ) as key:
                winreg.SetValueEx(key, value_name, 0, value_type, value)
                return f"Successfully wrote '{value_name}' to '{hive_name}\\{sub_key}'"
        except PermissionError as e:
            raise ToolOperationError(
                "access_denied",
                f"Access denied. Administrator privileges required to write to {hive_name}\\{sub_key}.",
                actions=[
                    "Run the server with elevated privileges.",
                    "Use 'Run as Administrator' or equivalent.",
                ],
            ) from e
        except Exception as e:
            raise ToolOperationError(
                "unexpected",
                f"Failed to write registry key {hive_name}\\{sub_key}: {str(e)}",
                actions=[
                    "Verify the registry path and value.",
                    "Check the value type.",
                    "Retry the request.",
                ],
            ) from e

    @guard("registry.delete_registry_key")
    @export_tool(
        name="delete_registry_key",
        logger=logging.getLogger(__name__),
        tags=["registry.delete_registry_key"],
    )
    async def delete_registry_key(
        self,
        ctx: Context,
        hive_name: str,
        sub_key: str,
        value_name: str,
        constraints: dict | None = None,
    ) -> str:
        """Deletes a specific value from the Windows registry."""
        hive = self.hives.get(hive_name.upper())
        if not hive:
            raise ToolOperationError(
                "validation",
                f"Invalid hive: {hive_name}",
                actions=[
                    "Use one of: HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE, HKEY_CLASSES_ROOT, HKEY_USERS, HKEY_CURRENT_CONFIG.",
                    "Retry with a valid hive name.",
                ],
            )
        try:
            permission = await request_elicitation_permission(
                ctx,
                f"Are you sure you want to delete this registry value in {hive_name}\\{sub_key} with name '{value_name}'? This can have significant effects on your system. Please confirm.",
            )
            if permission is None:
                raise ToolOperationError(
                    "auth_required",
                    "Cannot delete from registry due to lack of elicitation capability.",
                    actions=[
                        "Ensure elicitation is enabled in the server configuration.",
                        "Retry the request.",
                    ],
                )
            if permission is False:
                self.logger.info(
                    f"User declined to delete registry key '{value_name}' in key {hive_name}\\{sub_key}."
                )
                return f"Operation cancelled by user. Value '{value_name}' was not deleted from registry key '{hive_name}\\{sub_key}'."

            with winreg.OpenKey(hive, sub_key, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, value_name)
                return f"Successfully deleted '{value_name}' from registry key '{hive_name}\\{sub_key}'"
        except FileNotFoundError as e:
            raise ToolOperationError(
                "not_found",
                f"Registry key or value not found: {value_name} in {hive_name}\\{sub_key}",
                actions=[
                    "Verify the hive, sub_key, and value_name.",
                    "Use list_registry_key to check available values.",
                ],
            ) from e
        except PermissionError as e:
            raise ToolOperationError(
                "access_denied",
                f"Access denied. Administrator privileges required to delete from {hive_name}\\{sub_key}.",
                actions=[
                    "Run the server with elevated privileges.",
                    "Use 'Run as Administrator' or equivalent.",
                ],
            ) from e

    @guard("registry.get_registry_value_types")
    @export_tool(
        name="get_registry_value_types",
        logger=logging.getLogger(__name__),
        tags=["registry.get_registry_value_types"],
    )
    def get_registry_value_types(
        self, ctx: Context, constraints: dict | None = None
    ) -> dict[int, str]:
        """Returns a list of valid registry value types."""
        return {type_id: description for type_id, description in self.REG_TYPE_DESCRIPTIONS.items()}

    @guard("registry.get_registry_hive_path")
    @export_tool(
        name="get_registry_hive_path",
        logger=logging.getLogger(__name__),
        tags=["registry.get_registry_hive_path"],
    )
    def get_registry_hive_path(
        self, ctx: Context, hive_name: str, constraints: dict | None = None
    ) -> int | None:
        """Returns the registry hive path for a given hive name."""
        return self.hives.get(hive_name.upper())

    # i need special priviliges for current process because its binary operations, too tedious
    # @export_tool(name="save_registry_key", logger=logging.getLogger(__name__))
    # async def save_registry_key(self, ctx: Context, hive_name: str, sub_key: str, output_path: str) -> str:
    #     """ Export one key in file using winreg.SaveKey and return the path to the exported file."""
    #     hive = self.hives.get(hive_name.upper())
    #     if not hive:
    #         raise ValueError(f"Error: Invalid hive: {hive_name}")

    #     await validate_path(output_path,ctx=ctx,must_exist=False,expected_type="file")

    #     try:
    #         with winreg.OpenKey(hive, sub_key, 0, winreg.KEY_READ) as key:
    #             winreg.SaveKey(key, output_path)
    #             return f"Successfully backed up registry key '{hive_name}\\{sub_key}' to '{output_path}'"
    #     except Exception as e:
    #         raise Exception(f"Error backing up registry key: {str(e)}") from e

    # LoadKey cannot load entire branches, it requires complex logic. i would just do it via reg import command line tool which can handle .reg files with multiple keys and values
    # @export_tool(name="load_registry_key", logger=logging.getLogger(__name__))
    # async def load_key_from_file(self, ctx: Context, hive_name: str, sub_key: str, file_path: str) -> str:
    #     """ Loads a registry key from a file and returns the path to the loaded file."""
    #     hive = self.hives.get(hive_name.upper())
    #     if not hive:
    #         raise ValueError(f"Error: Invalid hive: {hive_name}")

    #     await validate_path(file_path,ctx=ctx,must_exist=True,expected_type="file")

    #     try:
    #         with winreg.OpenKey(hive, sub_key, 0, winreg.KEY_WRITE) as key:
    #             winreg.LoadKey(key, file_path)
    #             return f"Successfully loaded registry key '{hive_name}\\{sub_key}' from '{file_path}'"
    #     except Exception as e:
    #         raise Exception(f"Error loading registry key: {str(e)}") from e

    @guard("registry.check_key_exists")
    def check_key_exists(
        self, ctx: Context, hive_name: str, sub_key: str, constraints: dict | None = None
    ) -> bool:
        """Checks if a specific registry key exists."""
        hive = self.hives.get(hive_name.upper())
        if not hive:
            raise ToolOperationError(
                "validation",
                f"Invalid hive: {hive_name}",
                actions=[
                    "Use one of: HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE, HKEY_CLASSES_ROOT, HKEY_USERS, HKEY_CURRENT_CONFIG.",
                    "Retry with a valid hive name.",
                ],
            )
        try:
            with winreg.OpenKey(hive, sub_key, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as _:
                return True
        except FileNotFoundError:
            return False
        except PermissionError as e:
            raise ToolOperationError(
                "access_denied",
                f"Access denied checking registry key {hive_name}\\{sub_key}.",
                actions=[
                    "Run the server with elevated privileges.",
                    "Use 'Run as Administrator' or equivalent.",
                ],
            ) from e
        except Exception as e:
            raise ToolOperationError(
                "unexpected",
                f"Error checking registry key {hive_name}\\{sub_key}: {str(e)}",
                actions=[
                    "Verify the hive and key path.",
                    "Retry the request.",
                ],
            ) from e

    def search_installed_software_in_registry(self):
        pass
