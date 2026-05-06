# Permissions mapping

Format: `resource.tool_name` — permission required to invoke the tool.

## Security Architecture

The current permission architecture has two layers:

1. The first layer is cosmetic filtering in the middleware via `_filter_tools`.
	It hides tools from the tools/list request for a specific role when that role does not have the required permission. Middleware checks user access to tool by tools tags sequence which includes permission name. This is not primarily a security boundary; it mainly prevents the AI agent from hallucinating tools and spamming inaccesible tools. If client does not see the tool, user may even never guess that it exists. 

2. The second layer is the real security boundary: the `@guard` decorator on the tool itself.
	Even if a client somehow learns the name of a hidden tool, for example `system.kill_process`, and sends a direct `tools/call` request that bypasses the tool list, the `@guard` decorator intercepts the call. It checks `user_id` and the user's role, and raises `PermissionError("Access Denied")`. The function execution never starts.

## Permissions list
- system.get_environment_variable: Read single environment variable (user or system scope).
- system.list_environment_variables: List environment variables (user or system scope).
- system.set_environment_variable: Set environment variable (may update registry).
- system.delete_environment_variable: Delete environment variable (may update registry).
- system.create_windows_restore_point: Create a Windows System Restore point.

 - registry.list_registry_key: List subkeys and values of a registry key.
 - registry.read_registry_key: Read a specific registry value.
 - registry.write_registry_key: Write a registry value (elicitation confirmation required).
 - registry.delete_registry_key: Delete a registry value (elicitation confirmation required).
 - registry.get_registry_value_types: Return supported registry value types.
 - registry.get_registry_hive_path: Resolve hive name to hive constant.
 - registry.check_key_exists: Check whether a registry key exists.

 - filesystem.list_files: List files and directories in a path.
 - filesystem.read_file: Read file contents (optionally include image sampling).
 - filesystem.write_file: Write file content (dangerous/admin level).
 - filesystem.create_directory: Create directory.
 - filesystem.list_directory_with_sizes: List directory with sizes and summary.
 - filesystem.analyze_directory_security: Run a security/content analysis on directory.
 - filesystem.get_file_info: Get detailed metadata about a file or directory.
 - filesystem.move_file: Move or rename files and directories.
 - filesystem.search_files: Search for files matching a glob pattern.
 - filesystem.read_multiple_files: Read contents of multiple files simultaneously.
 - filesystem.delete_file: Delete a file (confirmation required).
 - filesystem.delete_directory: Delete a directory recursively (confirmation required).
 - filesystem.filesystem_summary: Get summary of filesystem at a path (size, file/dir counts).
 - filesystem.get_creative_file_description: Generate creative description of file contents using AI sampling.

 - process.list_processes: Enumerate running processes (filtering supported).
 - process.get_current_username: Get username of process owner (server user).
 - process.get_process_info: Get snapshot for a single PID.
 - process.get_detailed_process_info: Get detailed diagnostics for a PID.
 - process.get_process_connections: Get network connections for a PID.
 - process.get_process_tree: Get parent/child tree for a PID.
 - process.get_process_open_files: List open files for a PID.

 - process.start_process: Start a process (validated commands list).
 - process.run_admin_shell: Run a raw shell command (dangerous, admin use only).
 - process.get_available_commands: Get commands available to `start_process`.
 - process.kill_process: Terminate a process (elicitation confirmation required).
 - process.suspend_process: Suspend a process (elicitation confirmation required).
 - process.resume_process: Resume a suspended process (elicitation confirmation required).
 - process.kill_process_tree: Terminate a process tree (elicitation confirmation required).

 - server.get_server_status: Retrieve overall server status and features.
 - server.list_allowed_roots: List currently allowed filesystem roots.
 - server.add_allowed_root: Add a path to allowed roots (admin).
 - server.update_roots: Replace allowed roots list (admin).
 - server.remove_root: Remove an allowed root (admin).
 - server.submit_error_report: Submit an error report to support.

 - monitoring.get_system_resource_usage: CPU/memory usage snapshot.
 - monitoring.get_disk_status: Disk partitions usage.
 - monitoring.get_system_info: Static system information (OS, hardware, uptime).

 - windowsos.backup_registry_keys: Export registry key to file.
 - windowsos.restore_registry_keys_from_file: Import registry keys from .reg file.

 - service.list_services: Enumerate Windows services with filters.
 - service.get_service_status: Get a single service status.
 - service.start_service: Start a service.
 - service.stop_service: Stop a service.
 - service.stop_service_with_deps: Stop a service and its dependencies.
 - service.restart_service: Restart a service.
 - service.change_service_startup_type: Change service startup type.
 - service.change_service_config: Update service configuration.
 - service.get_service_logs: Read recent event log entries for a service.
 - service.create_service: Install/create a new Windows service.
 - service.delete_service: Delete an installed service.
 - service.wrap_script_as_service: Wrap a script as a service using Servy.


## How to build policy config.
The policy.json file is the core of security layer. It maps users to roles and roles to specific capabilities and restrictions.

Below is an example of how it may look like:

```json
{
  "roles": {
    "admin": {
      "permissions": ["*"],
      "constraints": {}
    },
    "developer": {
      "permissions": [
        "filesystem.list_files",
        "filesystem.read_file",
        "filesystem.write_file",
        "filesystem.create_directory",
        "filesystem.move_file",
        "filesystem.search_files",
        "filesystem.get_file_info",
        "process.list_processes",
        "process.get_process_info",
        "process.get_process_tree",
        "process.start_process",
        "process.get_available_commands",
        "monitoring.get_system_resource_usage",
        "monitoring.get_system_info",
        "server.get_server_status",
        "server.list_allowed_roots"
      ],
      "constraints": {
        "filesystem.read_file": {
          "allowed_paths": [
            "G:/Koblenzessentials/Projects",
            "C:/Users/*/Documents/Projects"
          ]
        },
        "filesystem.write_file": {
          "allowed_paths": [
            "G:/Koblenzessentials/Projects"
          ]
        },
        "process.start_process": {
          "allowed_commands": [
            "git",
            "npm",
            "node",
            "python",
            "pip",
            "cargo",
            "dotnet"
          ],
          "blocked_commands": [
            "format",
            "del",
            "rm",
            "rmdir"
          ]
        }
      }
    },
    "analyst": {
      "permissions": [
        "filesystem.list_files",
        "filesystem.read_file",
        "filesystem.read_multiple_files",
        "filesystem.search_files",
        "filesystem.get_file_info",
        "filesystem.filesystem_summary",
        "process.list_processes",
        "process.get_process_info",
        "process.get_process_connections",
        "monitoring.get_system_resource_usage",
        "monitoring.get_disk_status",
        "monitoring.get_system_info",
        "server.get_server_status"
      ],
      "constraints": {
        "filesystem.read_file": {
          "allowed_paths": [
            "G:/Koblenzessentials/Projects",
            "C:/Logs"
          ]
        }
      }
    },
    "guest": {
      "permissions": [
        "monitoring.get_system_info",
        "server.get_server_status"
      ],
      "constraints": {}
    }
  },
  "users": {
    "75110071": {
      "role": "admin",
      "username": "LyaKonch"
    },
    "dev-user-001": {
      "role": "developer",
      "username": "john.developer"
    },
    "analyst-user-001": {
      "role": "analyst",
      "username": "jane.analyst"
    },
    "guest-user-001": {
      "role": "guest",
      "username": "public.viewer"
    }
  }
}
```

## Components you have to change
### A. Roles Section ("roles")

This is where you define the blueprints for access levels.

- Permissions: A list of strings. Each string corresponds to the identifier used in your @guard("id") decorator.

    - God Mode: Use ["*"] to grant access to every tool.

- Constraints: This is the "ABAC" part. You can define custom key-value pairs that your tools will use to filter actions.

    - allowed_paths: Limit the LLM to specific directories. Note that you should also consider global allowed_paths.

    - allowed_commands: A whitelist of shell commands.
    
    - Each tool can have its own constraints. Refer to the tool's implementation or documentation to see what constraint keys it supports and how to configure them.

### B. Users Section ("users")
This maps real-world identities to your roles.
- The Key: This must be a string representation of the GitHub User ID (e.g., "75110071").

- The Role: Must match one of the keys defined in the "roles" section.

- When client is connected and his role meanwhile is changed, user must reconnect in order to get new list of tools. If you have just changed role permissions or role contrainst, its okay - file is being read every time the permission is checked. 

### General recomendations

- Default Role: If a new user connects, PolicyManager is designed to auto-register them as a guest. Periodically check the users section to promote these users to desired role.

- Be Specific with Constraints: Instead of blocking some command, it’s better to only whitelist commands you allow. It's safer to say what is allowed than what isn't.

- Pathing: Always use forward slashes (/) or escaped backslashes (\\) in JSON for Windows paths to avoid parsing errors.