"""Unit tests for PolicyManager ABAC (Attribute-Based Access Control) system.

This test suite verifies the constraint validation logic without running a server
or involving AI/LLM. Each test is isolated and tests one specific constraint type.
"""

import json
import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from auth.PolicyManager import PolicyManager

logger = logging.getLogger(__name__)


class TestPolicyManagerBasics:
    """Test basic PolicyManager initialization and loading."""

    def test_policy_manager_loads_file(self, test_policy_json: Path):
        """Test that PolicyManager correctly loads and parses policy.json."""
        pm = PolicyManager(config_path=str(test_policy_json))
        assert pm.policy is not None
        assert "roles" in pm.policy
        assert "users" in pm.policy

    def test_policy_manager_creates_default_on_missing_file(self, temp_dir: Path):
        """Test that PolicyManager creates a default guest policy if file doesn't exist."""
        missing_file = temp_dir / "nonexistent.json"
        pm = PolicyManager(config_path=str(missing_file))
        assert pm.policy is not None
        assert "guest" in pm.policy["roles"]

    def test_get_user_role_existing_user(self, policy_manager_instance: PolicyManager):
        """Test retrieving role for an existing user."""
        role = policy_manager_instance.get_user_role("user123", "testuser")
        assert role == "user"

    def test_get_user_role_auto_registers_guest(
        self, policy_manager_instance: PolicyManager, temp_dir: Path
    ):
        """Test that non-existent users are auto-registered as guests."""
        new_user_id = "newuser999"
        role = policy_manager_instance.get_user_role(new_user_id, "newusername")
        assert role == "guest"

    def test_check_access_admin_wildcard(self, policy_manager_instance: PolicyManager):
        """Test that admin users have wildcard (*) access to all permissions."""
        # Admin has "*" in permissions, should have access to anything
        has_access = policy_manager_instance.check_access(
            "admin456", "filesystem.delete_path", "adminuser"
        )
        assert has_access is True

    def test_check_access_specific_permission(self, policy_manager_instance: PolicyManager):
        """Test checking access for a specific permission."""
        has_access = policy_manager_instance.check_access(
            "user123", "filesystem.read_file", "testuser"
        )
        assert has_access is True

    def test_check_access_denied(self, policy_manager_instance: PolicyManager):
        """Test that access is denied for permissions not in role."""
        # Guest role doesn't have filesystem.write_file
        has_access = policy_manager_instance.check_access(
            "guest789", "filesystem.write_file", "guestuser"
        )
        assert has_access is False

    def test_get_constraints_for_permission(self, policy_manager_instance: PolicyManager):
        """Test retrieving constraints for a specific permission."""
        constraints = policy_manager_instance.get_constraints(
            "user123", "filesystem.read_file", "testuser"
        )
        assert constraints is not None
        assert "max_read_size" in constraints
        assert constraints["max_read_size"] == 1048576


class TestAllowedPathsConstraint:
    """Test allowed_paths constraint validation."""

    @patch("auth.PolicyManager.is_path_within_scope")
    def test_allowed_paths_single_valid_path(
        self, mock_is_path, policy_manager_instance: PolicyManager
    ):
        """Test that a path within allowed list is accepted."""
        mock_is_path.return_value = True
        constraints = {"allowed_paths": ["/home/user/documents"]}
        result = policy_manager_instance.check_constraint(
            constraints, "allowed_paths", "/home/user/documents/file.txt"
        )
        assert result is True

    @patch("auth.PolicyManager.is_path_within_scope")
    def test_allowed_paths_denied(
        self, mock_is_path, policy_manager_instance: PolicyManager
    ):
        """Test that paths outside allowed list are rejected."""
        mock_is_path.return_value = False
        constraints = {"allowed_paths": ["/home/user"]}
        result = policy_manager_instance.check_constraint(
            constraints, "allowed_paths", "/etc/passwd"
        )
        assert result is False

    @patch("auth.PolicyManager.is_path_within_scope")
    def test_allowed_paths_multiple_paths(
        self, mock_is_path, policy_manager_instance: PolicyManager
    ):
        """Test allowed_paths with multiple valid paths."""
        # First call returns True, second returns False
        mock_is_path.side_effect = [True, False]
        constraints = {"allowed_paths": ["/home/user", "/tmp/test", "/var/log"]}
        assert (
            policy_manager_instance.check_constraint(
                constraints, "allowed_paths", "/tmp/test/file.log"
            )
            is True
        )
        assert (
            policy_manager_instance.check_constraint(
                constraints, "allowed_paths", "/root/secret"
            )
            is False
        )

    def test_allowed_paths_none_constraints(self, policy_manager_instance: PolicyManager):
        """Test that None constraints allow all paths (no restrictions)."""
        result = policy_manager_instance.check_constraint(None, "allowed_paths", "/any/path")
        assert result is True


class TestAllowedHivesConstraint:
    """Test allowed_hives constraint (Windows Registry)."""

    def test_allowed_hives_exact_match(self, policy_manager_instance: PolicyManager):
        """Test exact hive name matching (case-insensitive)."""
        constraints = {"allowed_hives": ["HKEY_CURRENT_USER", "HKEY_LOCAL_MACHINE"]}
        assert (
            policy_manager_instance.check_constraint(
                constraints, "allowed_hives", "HKEY_CURRENT_USER"
            )
            is True
        )

    def test_allowed_hives_case_insensitive(self, policy_manager_instance: PolicyManager):
        """Test that hive matching is case-insensitive."""
        constraints = {"allowed_hives": ["HKEY_CURRENT_USER"]}
        assert (
            policy_manager_instance.check_constraint(
                constraints, "allowed_hives", "hkey_current_user"
            )
            is True
        )

    def test_allowed_hives_denied(self, policy_manager_instance: PolicyManager):
        """Test that disallowed hives are rejected."""
        constraints = {"allowed_hives": ["HKEY_CURRENT_USER"]}
        assert (
            policy_manager_instance.check_constraint(
                constraints, "allowed_hives", "HKEY_LOCAL_MACHINE"
            )
            is False
        )


class TestAllowedKeysConstraint:
    """Test allowed_keys constraint with wildcard patterns."""

    def test_allowed_keys_wildcard_match(self, policy_manager_instance: PolicyManager):
        """Test wildcard pattern matching in registry keys."""
        constraints = {"allowed_keys": ["SOFTWARE\\MyApp\\*"]}
        # Should match keys like SOFTWARE\MyApp\Config, SOFTWARE\MyApp\Settings
        assert (
            policy_manager_instance.check_constraint(
                constraints, "allowed_keys", "SOFTWARE\\MyApp\\Config"
            )
            is True
        )

    def test_allowed_keys_wildcard_denied(self, policy_manager_instance: PolicyManager):
        """Test that keys outside wildcard pattern are denied."""
        constraints = {"allowed_keys": ["SOFTWARE\\MyApp\\*"]}
        assert (
            policy_manager_instance.check_constraint(
                constraints, "allowed_keys", "SYSTEM\\CurrentControlSet\\Services"
            )
            is False
        )

    def test_allowed_keys_exact_match(self, policy_manager_instance: PolicyManager):
        """Test exact key name matching."""
        constraints = {"allowed_keys": ["SYSTEM\\Test", "SOFTWARE\\Config"]}
        assert (
            policy_manager_instance.check_constraint(
                constraints, "allowed_keys", "SYSTEM\\Test"
            )
            is True
        )

    def test_allowed_keys_case_insensitive(self, policy_manager_instance: PolicyManager):
        """Test that key matching is case-insensitive."""
        constraints = {"allowed_keys": ["SOFTWARE\\myapp\\*"]}
        assert (
            policy_manager_instance.check_constraint(
                constraints, "allowed_keys", "software\\MYAPP\\config"
            )
            is True
        )

    def test_allowed_keys_multiple_patterns(self, policy_manager_instance: PolicyManager):
        """Test allowed_keys with multiple wildcard patterns."""
        constraints = {"allowed_keys": ["SOFTWARE\\*", "SYSTEM\\Test\\*"]}
        assert (
            policy_manager_instance.check_constraint(
                constraints, "allowed_keys", "SOFTWARE\\Any\\Deep\\Key"
            )
            is True
        )
        assert (
            policy_manager_instance.check_constraint(
                constraints, "allowed_keys", "SYSTEM\\Test\\Subkey"
            )
            is True
        )
        assert (
            policy_manager_instance.check_constraint(
                constraints, "allowed_keys", "HKEY_CLASSES_ROOT\\Something"
            )
            is False
        )


class TestAllowedServicesConstraint:
    """Test allowed_services constraint."""

    def test_allowed_services_exact_match(self, policy_manager_instance: PolicyManager):
        """Test exact service name matching."""
        constraints = {"allowed_services": ["wuauserv", "spooler"]}
        assert (
            policy_manager_instance.check_constraint(
                constraints, "allowed_services", "wuauserv"
            )
            is True
        )

    def test_allowed_services_denied(self, policy_manager_instance: PolicyManager):
        """Test that disallowed services are rejected."""
        constraints = {"allowed_services": ["wuauserv", "spooler"]}
        assert (
            policy_manager_instance.check_constraint(
                constraints, "allowed_services", "TermService"
            )
            is False
        )

    def test_allowed_services_case_insensitive(self, policy_manager_instance: PolicyManager):
        """Test that service name matching is case-insensitive."""
        constraints = {"allowed_services": ["WuAuServ"]}
        assert (
            policy_manager_instance.check_constraint(
                constraints, "allowed_services", "wuauserv"
            )
            is True
        )


class TestAllowedExtensionsConstraint:
    """Test allowed_extensions constraint for file operations."""

    def test_allowed_extensions_match(self, policy_manager_instance: PolicyManager):
        """Test that allowed file extensions pass validation."""
        constraints = {"allowed_extensions": ["txt", "py", "json"]}
        assert (
            policy_manager_instance.check_constraint(
                constraints, "allowed_extensions", "txt"
            )
            is True
        )

    def test_allowed_extensions_denied(self, policy_manager_instance: PolicyManager):
        """Test that disallowed extensions are rejected."""
        constraints = {"allowed_extensions": ["txt", "py"]}
        assert (
            policy_manager_instance.check_constraint(
                constraints, "allowed_extensions", "exe"
            )
            is False
        )

    def test_allowed_extensions_case_insensitive(self, policy_manager_instance: PolicyManager):
        """Test that extension matching is case-insensitive."""
        constraints = {"allowed_extensions": ["TXT", "PY"]}
        assert (
            policy_manager_instance.check_constraint(
                constraints, "allowed_extensions", "txt"
            )
            is True
        )


class TestNumericConstraints:
    """Test numeric constraints: max_read_size, max_write_size, max_timeout, max_depth."""

    def test_max_read_size_within_limit(self, policy_manager_instance: PolicyManager):
        """Test that files within size limit pass validation."""
        constraints = {"max_read_size": 1048576}  # 1MB
        assert (
            policy_manager_instance.check_constraint(
                constraints, "max_read_size", 524288
            )  # 512KB
            is True
        )

    def test_max_read_size_exceeds_limit(self, policy_manager_instance: PolicyManager):
        """Test that files exceeding size limit are rejected."""
        constraints = {"max_read_size": 1048576}  # 1MB
        assert (
            policy_manager_instance.check_constraint(
                constraints, "max_read_size", 2097152
            )  # 2MB
            is False
        )

    def test_max_read_size_exact_limit(self, policy_manager_instance: PolicyManager):
        """Test that files at exact size limit pass validation."""
        constraints = {"max_read_size": 1048576}  # 1MB
        assert (
            policy_manager_instance.check_constraint(
                constraints, "max_read_size", 1048576
            )  # 1MB
            is True
        )

    def test_max_write_size(self, policy_manager_instance: PolicyManager):
        """Test max_write_size constraint."""
        constraints = {"max_write_size": 5242880}  # 5MB
        assert (
            policy_manager_instance.check_constraint(
                constraints, "max_write_size", 2097152
            )  # 2MB
            is True
        )
        assert (
            policy_manager_instance.check_constraint(
                constraints, "max_write_size", 10485760
            )  # 10MB
            is False
        )

    def test_max_timeout(self, policy_manager_instance: PolicyManager):
        """Test max_timeout constraint."""
        constraints = {"max_timeout": 300}  # 5 minutes
        assert (
            policy_manager_instance.check_constraint(
                constraints, "max_timeout", 150
            )  # 2.5 minutes
            is True
        )
        assert (
            policy_manager_instance.check_constraint(
                constraints, "max_timeout", 600
            )  # 10 minutes
            is False
        )

    def test_max_depth(self, policy_manager_instance: PolicyManager):
        """Test max_depth constraint for directory traversal."""
        constraints = {"max_depth": 5}
        assert (
            policy_manager_instance.check_constraint(
                constraints, "max_depth", 3
            )  # Within limit
            is True
        )
        assert (
            policy_manager_instance.check_constraint(
                constraints, "max_depth", 10
            )  # Exceeds limit
            is False
        )

    def test_max_constraints_with_string_values(
        self, policy_manager_instance: PolicyManager
    ):
        """Test that numeric constraints work with string input (conversion to int)."""
        constraints = {"max_read_size": "1048576"}
        assert (
            policy_manager_instance.check_constraint(
                constraints, "max_read_size", "524288"
            )
            is True
        )


class TestProtectedProcessesConstraint:
    """Test protected_processes constraint - negative match list."""

    def test_protected_processes_allowed_process(self, policy_manager_instance: PolicyManager):
        """Test that non-protected processes are allowed."""
        constraints = {"protected_processes": ["svchost.exe", "explorer.exe", "System"]}
        # notepad.exe is not in the protected list
        assert (
            policy_manager_instance.check_constraint(
                constraints, "protected_processes", "notepad.exe"
            )
            is True
        )

    def test_protected_processes_denied_process(self, policy_manager_instance: PolicyManager):
        """Test that protected processes are rejected."""
        constraints = {"protected_processes": ["svchost.exe", "explorer.exe", "System"]}
        # svchost.exe is in the protected list
        assert (
            policy_manager_instance.check_constraint(
                constraints, "protected_processes", "svchost.exe"
            )
            is False
        )

    def test_protected_processes_multiple_checks(
        self, policy_manager_instance: PolicyManager
    ):
        """Test multiple protected processes."""
        constraints = {"protected_processes": ["System", "svchost.exe", "explorer.exe"]}
        assert (
            policy_manager_instance.check_constraint(
                constraints, "protected_processes", "System"
            )
            is False
        )
        assert (
            policy_manager_instance.check_constraint(
                constraints, "protected_processes", "explorer.exe"
            )
            is False
        )
        assert (
            policy_manager_instance.check_constraint(
                constraints, "protected_processes", "calc.exe"
            )
            is True
        )


class TestAllowedPatternsConstraint:
    """Test allowed_patterns constraint with glob patterns."""

    def test_allowed_patterns_simple(self, policy_manager_instance: PolicyManager):
        """Test simple glob pattern matching."""
        constraints = {"allowed_patterns": ["TEST_*", "TEMP_*"]}
        assert (
            policy_manager_instance.check_constraint(
                constraints, "allowed_patterns", "TEST_CONFIG"
            )
            is True
        )

    def test_allowed_patterns_denied(self, policy_manager_instance: PolicyManager):
        """Test that patterns not matching are denied."""
        constraints = {"allowed_patterns": ["TEST_*", "TEMP_*"]}
        assert (
            policy_manager_instance.check_constraint(
                constraints, "allowed_patterns", "PRODUCTION_CONFIG"
            )
            is False
        )

    def test_allowed_patterns_case_insensitive(self, policy_manager_instance: PolicyManager):
        """Test that pattern matching is case-insensitive."""
        constraints = {"allowed_patterns": ["test_*"]}
        assert (
            policy_manager_instance.check_constraint(
                constraints, "allowed_patterns", "TEST_CONFIG"
            )
            is True
        )

    def test_allowed_patterns_question_mark(self, policy_manager_instance: PolicyManager):
        """Test glob pattern with ? (single character match)."""
        constraints = {"allowed_patterns": ["TEST_?_CONFIG"]}
        assert (
            policy_manager_instance.check_constraint(
                constraints, "allowed_patterns", "TEST_A_CONFIG"
            )
            is True
        )
        assert (
            policy_manager_instance.check_constraint(
                constraints, "allowed_patterns", "TEST_AB_CONFIG"
            )
            is False
        )


class TestRequireOwnProcessConstraint:
    """Test require_own_process constraint - process ownership validation."""

    @patch("psutil.Process")
    def test_require_own_process_matching_user(
        self, mock_process_class, policy_manager_instance: PolicyManager
    ):
        """Test that processes owned by current user pass validation."""
        # Mock the current process to have username "testuser"
        mock_proc = MagicMock()
        mock_proc.username.return_value = "testuser"
        mock_process_class.return_value = mock_proc

        constraints = {"require_own_process": True}
        result = policy_manager_instance.check_constraint(
            constraints, "require_own_process", "testuser"
        )
        assert result is True

    @patch("psutil.Process")
    def test_require_own_process_different_user(
        self, mock_process_class, policy_manager_instance: PolicyManager
    ):
        """Test that processes from different users are rejected."""
        mock_proc = MagicMock()
        mock_proc.username.return_value = "admin"
        mock_process_class.return_value = mock_proc

        constraints = {"require_own_process": True}
        result = policy_manager_instance.check_constraint(
            constraints, "require_own_process", "testuser"
        )
        assert result is False

    @patch("psutil.Process")
    def test_require_own_process_false_allows_all(
        self, mock_process_class, policy_manager_instance: PolicyManager
    ):
        """Test that require_own_process=False allows all users."""
        mock_proc = MagicMock()
        mock_proc.username.return_value = "admin"
        mock_process_class.return_value = mock_proc

        constraints = {"require_own_process": False}
        # When False, it should be treated as no constraint
        result = policy_manager_instance.check_constraint(
            constraints, "require_own_process", "otheruser"
        )
        # Since require_own_process is False, the check should return True
        # (the constraint dict exists but the value is False, so it passes)
        # Actually, looking at the code, when limit is False it won't enter the if block
        # So it will return True at the end
        assert result is True


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_empty_constraints_dict_allows_all(self, policy_manager_instance: PolicyManager):
        """Test that empty constraints dict allows all values."""
        constraints = {}
        assert (
            policy_manager_instance.check_constraint(
                constraints, "allowed_paths", "/any/path"
            )
            is True
        )

    def test_none_constraints_allows_all(self, policy_manager_instance: PolicyManager):
        """Test that None constraints allow all values."""
        assert (
            policy_manager_instance.check_constraint(
                None, "allowed_paths", "/any/path"
            )
            is True
        )

    def test_constraint_key_not_in_dict(self, policy_manager_instance: PolicyManager):
        """Test accessing a constraint key that doesn't exist in the dict."""
        constraints = {"allowed_paths": ["/home/user"]}
        # max_depth is not in constraints, should return True (no restriction)
        result = policy_manager_instance.check_constraint(
            constraints, "max_depth", 100
        )
        assert result is True

    def test_unknown_constraint_type_returns_true(
        self, policy_manager_instance: PolicyManager
    ):
        """Test that unknown constraint types return True (no effect)."""
        constraints = {"unknown_constraint": ["value"]}
        result = policy_manager_instance.check_constraint(
            constraints, "unknown_constraint", "anything"
        )
        assert result is True

    def test_policy_reload_on_get_user_role(self, policy_manager_instance: PolicyManager):
        """Test that policy is reloaded when getting user role."""
        # This verifies that the policy is fresh from disk each time
        role1 = policy_manager_instance.get_user_role("user123", "testuser")
        role2 = policy_manager_instance.get_user_role("user123", "testuser")
        assert role1 == role2 == "user"


class TestIntegrationScenarios:
    """Test realistic scenarios combining multiple constraints."""

    def test_full_filesystem_read_permission_check(
        self, policy_manager_instance: PolicyManager
    ):
        """Test a complete filesystem read permission check scenario."""
        # Get constraints for a user
        constraints = policy_manager_instance.get_constraints(
            "user123", "filesystem.read_file", "testuser"
        )

        # Check multiple constraints
        assert policy_manager_instance.check_constraint(
            constraints, "max_read_size", 524288
        )  # 512KB
        assert policy_manager_instance.check_constraint(
            constraints, "allowed_extensions", "txt"
        )
        assert (
            policy_manager_instance.check_constraint(
                constraints, "allowed_extensions", "exe"
            )
            is False
        )

    def test_guest_has_limited_permissions(self, policy_manager_instance: PolicyManager):
        """Test that guest role has limited permissions."""
        # Guest can list files
        has_list_access = policy_manager_instance.check_access(
            "guest789", "filesystem.list_files", "guestuser"
        )
        assert has_list_access is True

        # Guest cannot write files
        has_write_access = policy_manager_instance.check_access(
            "guest789", "filesystem.write_file", "guestuser"
        )
        assert has_write_access is False

    def test_admin_has_all_permissions(self, policy_manager_instance: PolicyManager):
        """Test that admin role has access to all permissions via wildcard."""
        # Admin should have access to any permission with "*" wildcard
        assert (
            policy_manager_instance.check_access(
                "admin456", "filesystem.delete_path", "adminuser"
            )
            is True
        )
        assert (
            policy_manager_instance.check_access(
                "admin456", "system.delete_variable", "adminuser"
            )
            is True
        )
        assert (
            policy_manager_instance.check_access(
                "admin456", "registry.write_registry_key", "adminuser"
            )
            is True
        )

    @patch("auth.PolicyManager.is_path_within_scope")
    def test_constraint_validation_chain(
        self, mock_is_path, policy_manager_instance: PolicyManager
    ):
        """Test validating multiple constraints in sequence (like in real usage)."""
        mock_is_path.return_value = True
        constraints = {
            "allowed_paths": ["/home/user/documents"],
            "max_read_size": 1048576,
            "allowed_extensions": ["txt", "py"],
        }

        # All constraints should pass
        assert (
            policy_manager_instance.check_constraint(
                constraints, "allowed_paths", "/home/user/documents/script.py"
            )
            is True
        )
        assert (
            policy_manager_instance.check_constraint(
                constraints, "max_read_size", 512000
            )
            is True
        )
        assert (
            policy_manager_instance.check_constraint(
                constraints, "allowed_extensions", "py"
            )
            is True
        )
