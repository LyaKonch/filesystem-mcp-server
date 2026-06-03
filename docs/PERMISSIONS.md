# Permissions mapping

Format: `resource.tool_name` — permission required to invoke the tool.

## Security Architecture

The current permission architecture has two layers:

1. The first layer is cosmetic filtering in the middleware via `_filter_tools`.
	It hides tools from the tools/list request for a specific role when that role does not have the required permission. Middleware checks user access to tool by tools tags sequence which includes permission name. This is not primarily a security boundary; it mainly prevents the AI agent from hallucinating tools and spamming inaccesible tools. If client does not see the tool, user may even never guess that it exists. 

2. The second layer is the real security boundary: the `guard` dependency on the tool itself.
	Even if a client somehow learns the name of a hidden tool, for example `system.kill_process`, and sends a direct `tools/call` request that bypasses the tool list, the `guard` dependency is being invoked before the tool starts. It checks `user_id` and the user's role, and raises `PermissionError("Access Denied")`. The function execution never starts.

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

 - filesystem.list_files: List files and directories in a path with filtering and recursion.
 - filesystem.read_file: Read file contents (optionally include image sampling).
 - filesystem.write_file: Write or append content to files (create new or overwrite).
 - filesystem.edit_file: Search and replace text in existing files safely.
 - filesystem.create_directory: Create a new directory with parent path creation.
 - filesystem.get_path_info: Get detailed metadata about a file or directory.
 - filesystem.move_file: Move or rename files and directories.
 - filesystem.search_files: Search for text content in directory tree.
 - filesystem.delete_path: Delete a file or directory (with recursion support).

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
      "permissions": [
        "*"
      ],
      "constraints": {}
    },
    "developer": {
      "permissions": [
        "process.list_processes",
        "process.start_process",
        "process.kill_process",
        "process.suspend_process",
        "process.resume_process",
        "filesystem.read_file",
        "system.get_variable",
        "system.list_variables",
        "system.set_variable",
        "system.delete_variable",
        "registry.list_registry_key",
        "registry.read_registry_key",
        "registry.write_registry_key",
        "registry.delete_registry_key",
        "service.list_services",
        "service.get_service_status",
        "service.start_service",
        "service.stop_service",
        "service.stop_service_with_deps",
        "service.restart_service",
        "service.change_service_startup_type",
        "service.change_service_config",
        "service.get_service_logs",
        "service.create_service",
        "service.delete_service",
        "service.wrap_script_as_service"
      ],
      "constraints": {
        "process.start_process": {
          "allowed_commands": [
            "git",
            "npm",
            "python",
            "pip",
            "notepad"
          ],
          "max_timeout": 120
        },
        "process.kill_process": {
          "require_own_process": true,
          "protected_processes": [
            "svchost.exe",
            "csrss.exe",
            "lsass.exe",
            "explorer.exe",
            "dwm.exe"
          ]
        },
        "process.suspend_process": {
          "require_own_process": true,
          "protected_processes": [
            "svchost.exe",
            "csrss.exe",
            "lsass.exe",
            "explorer.exe",
            "dwm.exe"
          ]
        },
        "process.resume_process": {
          "require_own_process": true,
          "protected_processes": [
            "svchost.exe",
            "csrss.exe",
            "lsass.exe",
            "explorer.exe",
            "dwm.exe"
          ]
        },
        "filesystem.read_file": {
          "allowed_paths": [
            "G:/Koblenzessentials/Технології захисту інформації/"
          ]
        },
        "system.get_variable": {
          "allowed_scopes": ["PROCESS", "USER"],
          "allowed_variables": ["PATH", "MY_APP_CONFIG"]
        },
        "system.list_variables": {
          "allowed_scopes": ["PROCESS", "USER"]
        },
        "system.set_variable": {
          "allowed_scopes": ["PROCESS", "USER"],
          "allowed_variables": ["MY_APP_CONFIG"]
        },
        "system.delete_variable": {
          "allowed_scopes": ["PROCESS", "USER"],
          "allowed_variables": ["MY_APP_CONFIG"]
        },
        "registry.list_registry_key": {
          "allowed_hives": [
            "HKEY_CURRENT_USER",
            "HKEY_LOCAL_MACHINE"
          ],
          "allowed_keys": [
            "Environment",
            "SOFTWARE\\MyCompany\\*"
          ]
        },
        "registry.read_registry_key": {
          "allowed_hives": [
            "HKEY_CURRENT_USER",
            "HKEY_LOCAL_MACHINE"
          ],
          "allowed_keys": [
            "Environment",
            "SOFTWARE\\MyCompany\\*"
          ]
        },
        "registry.write_registry_key": {
          "allowed_hives": [
            "HKEY_CURRENT_USER",
            "HKEY_LOCAL_MACHINE"
          ],
          "allowed_keys": [
            "Environment",
            "SOFTWARE\\MyCompany\\*"
          ]
        },
        "registry.delete_registry_key": {
          "allowed_hives": [
            "HKEY_CURRENT_USER",
            "HKEY_LOCAL_MACHINE"
          ],
          "allowed_keys": [
            "Environment",
            "SOFTWARE\\MyCompany\\*"
          ]
        },
        "service.list_services": {
          "allowed_services": [
            "Spooler",
            "W32Time",
            "MyService"
          ]
        },
        "service.get_service_status": {
          "allowed_services": [
            "Spooler",
            "W32Time",
            "MyService"
          ]
        },
        "service.start_service": {
          "allowed_services": [
            "Spooler",
            "W32Time",
            "MyService"
          ]
        },
        "service.stop_service": {
          "allowed_services": [
            "Spooler",
            "W32Time",
            "MyService"
          ]
        },
        "service.stop_service_with_deps": {
          "allowed_services": [
            "Spooler",
            "W32Time",
            "MyService"
          ]
        },
        "service.restart_service": {
          "allowed_services": [
            "Spooler",
            "W32Time",
            "MyService"
          ]
        },
        "service.change_service_startup_type": {
          "allowed_services": [
            "Spooler",
            "W32Time",
            "MyService"
          ]
        },
        "service.change_service_config": {
          "allowed_services": [
            "Spooler",
            "W32Time",
            "MyService"
          ]
        },
        "service.get_service_logs": {
          "allowed_services": [
            "Spooler",
            "W32Time",
            "MyService"
          ]
        },
        "service.create_service": {
          "allowed_services": [
            "MyService"
          ],
          "allowed_paths": [
            "G:/Projects",
            "C:/Python314/python.exe"
          ]
        },
        "service.delete_service": {
          "allowed_services": [
            "MyService"
          ]
        },
        "service.wrap_script_as_service": {
          "allowed_services": [
            "MyService"
          ],
          "allowed_paths": [
            "G:/Projects",
            "C:/Python314/python.exe"
          ]
        }
      }
    },
    "guest": {
      "permissions": [
        "filesystem.list_files",
        "filesystem.get_path_info",
        "filesystem.read_file",
        "filesystem.write_file",
        "filesystem.edit_file",
        "filesystem.search_files"
      ],
      "constraints": {
        "filesystem.list_files": {
          "allowed_paths": [
            "G:/Projects/"
          ],
          "max_depth": 2
        },
         "filesystem.get_path_info": {
          "allowed_paths": [
            "G:/Projects/"
          ],
          "max_depth": 2
         },
         "filesystem.read_file": {
            "allowed_paths": [
              "G:/Projects/"
            ],
            "max_read_size": 10485760 
         },
         "filesystem.write_file": {
          "allowed_paths": [
              "G:/Projects/"
            ],
            "max_write_size": 10485760
         },
         "filesystem.search_files": {
          "allowed_paths": [
            "G:/Projects/"
          ]
         }
      }
    }
  },
  "users": {
    "12345": {
      "role": "guest",
      "username": "boss"
    },
    "75110071": {
      "role": "developer",
      "username": "LyaKonch"
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

## Constraints Reference Table

### Filesystem Tools

| Constraint Key | Tools | Purpose | Example |
|---|---|---|---|
| `allowed_paths` | list_files, read_file, write_file, edit_file, create_directory, get_path_info, move_file, search_files, delete_path | Whitelist of accessible directories (global access control) | `["G:/Projects", "C:/Data"]` |
| `max_read_size` | read_file, edit_file | Limit file size for read operations (prevents agent memory overflow) | `10485760` (10 MB) |
| `max_write_size` | write_file | Limit file size for write operations (prevents disk spam) | `5242880` (5 MB) |
| `max_depth` | list_files, get_path_info, search_files | Maximum recursion depth to prevent scanning entire disk | `5` |

### Process Tools

| Constraint Key | Permissions | Purpose | Example |
|---|---|---|---|
| `allowed_commands` | start_process | Whitelist of allowed shell commands that users can execute | `["git", "npm", "python", "pip"]` |
| `max_timeout` | start_process, run_admin_shell | Maximum execution time in seconds for commands (capped to this limit) | `60` (60 seconds max) |
| `require_own_process` | kill_process, suspend_process, resume_process, kill_process_tree | Allow users to only modify processes owned by their username | `true` (recommended) |
| `protected_processes` | kill_process, suspend_process, resume_process, kill_process_tree | List of process names that cannot be modified (safeguard system processes) | `["svchost.exe", "csrss.exe", "lsass.exe"]` |

### System Tools

| Constraint Key | Permissions | Purpose | Example |
|---|---|---|---|
| `allowed_scopes` | system.get_variable, system.list_variables, system.set_variable, system.delete_variable | Allowed environment scopes (e.g., PROCESS, USER, SYSTEM). Limits which scopes can be accessed. | `["PROCESS", "USER", "SYSTEM"]` |
| `allowed_variables` | system.get_variable, system.set_variable, system.delete_variable | Whitelist of environment variable names that may be read/modified. Supports exact names or patterns. | `["PATH", "MY_APP_CONFIG"]` |

### Registry Tools

| Constraint Key | Permissions | Purpose | Example |
|---|---|---|---|
| `allowed_hives` | registry.list_registry_key, registry.read_registry_key, registry.write_registry_key, registry.delete_registry_key | Whitelist of registry hives that can be accessed. | `["HKEY_CURRENT_USER", "HKEY_LOCAL_MACHINE"]` |
| `allowed_keys` | registry.list_registry_key, registry.read_registry_key, registry.write_registry_key, registry.delete_registry_key | Whitelist or patterns of registry subkeys that may be read/modified. | `["Environment", "SOFTWARE\\MyCompany\\*"]` |

### Service Tools

| Constraint Key | Permissions | Purpose | Example |
|---|---|---|---|
| `allowed_services` | service.list_services, service.get_service_status, service.start_service, service.stop_service, service.stop_service_with_deps, service.restart_service, service.change_service_startup_type, service.change_service_config, service.get_service_logs, service.create_service, service.delete_service, service.wrap_script_as_service | Whitelist of service names that can be listed or modified. The tool checks the service short name against this list before acting. | `["Spooler", "W32Time", "MyService"]` |
| `allowed_paths` | service.create_service, service.wrap_script_as_service | Whitelist of executable/script paths used when creating or wrapping a service. Applies to `binary_path`, `executor_path`, and `script_path`. | `["G:/Projects", "C:/Tools"]` |

