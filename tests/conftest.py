"""Shared test fixtures and configuration for all tests."""

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, AsyncMock

import pytest

# Configure logging for tests
logging.basicConfig(level=logging.DEBUG)


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Provide a temporary directory for testing file operations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_policy_json(temp_dir: Path) -> Path:
    """Create a test policy.json file with sample roles and permissions."""
    policy = {
        "roles": {
            "guest": {
                "permissions": ["filesystem.list_files", "monitoring.get_system_info"],
                "constraints": {
                    "filesystem.list_files": {
                        "allowed_paths": [str(temp_dir)],
                        "max_depth": 3,
                    },
                },
            },
            "user": {
                "permissions": [
                    "filesystem.list_files",
                    "filesystem.read_file",
                    "filesystem.write_file",
                    "monitoring.get_system_info",
                ],
                "constraints": {
                    "filesystem.list_files": {
                        "allowed_paths": [str(temp_dir), "/home/user"],
                        "max_depth": 5,
                    },
                    "filesystem.read_file": {
                        "max_read_size": 1048576,  # 1MB
                        "allowed_extensions": ["txt", "py", "json"],
                    },
                    "filesystem.write_file": {
                        "allowed_paths": [str(temp_dir)],
                        "max_write_size": 5242880,  # 5MB
                    },
                },
            },
            "admin": {
                "permissions": ["*"],  # Admin has all permissions
                "constraints": {},  # No constraints
            },
        },
        "users": {
            "user123": {"role": "user", "username": "testuser"},
            "admin456": {"role": "admin", "username": "adminuser"},
            "guest789": {"role": "guest", "username": "guestuser"},
        },
    }

    policy_file = temp_dir / "policy.json"
    policy_file.write_text(json.dumps(policy, indent=2))
    return policy_file


@pytest.fixture
def mock_context(temp_dir: Path):
    """Create a mock FastMCP Context object with async support and allowed roots."""
    from unittest.mock import AsyncMock
    
    ctx = MagicMock()
    ctx.session = MagicMock()
    ctx.session.id = "test-session-123"
    ctx.request_id = "test-request-456"
    
    # Mock list_roots as async method that returns test temp_dir as allowed root
    async def mock_list_roots():
        class MockRoot:
            uri = f"file:///{temp_dir}"
            name = "test_root"
        return [MockRoot()]
    
    ctx.list_roots = AsyncMock(side_effect=mock_list_roots)
    ctx.session.capabilities = MagicMock()
    ctx.session.capabilities.roots = True
    
    # Mock elicit to always accept operations
    async def mock_elicit(reason, response_type):
        class MockPermission:
            action = "accept"
            data = True
        return MockPermission()
    
    ctx.elicit = AsyncMock(side_effect=mock_elicit)
    
    return ctx


@pytest.fixture
def policy_manager_instance(test_policy_json: Path):
    """Create a PolicyManager instance with test policy file.
    
    This fixture imports PolicyManager dynamically to avoid import errors
    if auth module is not yet initialized.
    """
    from auth.PolicyManager import PolicyManager

    # Create instance with test policy file
    pm = PolicyManager(config_path=str(test_policy_json))
    return pm


@pytest.fixture
def sample_constraints() -> dict:
    """Provide a dictionary of sample constraints for testing."""
    return {
        "allowed_paths": ["/home/user", "/tmp/test"],
        "allowed_hives": ["HKEY_CURRENT_USER", "HKEY_LOCAL_MACHINE"],
        "allowed_keys": ["SOFTWARE\\MyApp\\*", "SYSTEM\\Test\\*"],
        "allowed_services": ["wuauserv", "spooler"],
        "allowed_extensions": ["txt", "py", "json"],
        "max_read_size": 1048576,  # 1MB
        "max_write_size": 5242880,  # 5MB
        "max_timeout": 300,  # 5 minutes
        "max_depth": 5,
        "protected_processes": ["svchost.exe", "explorer.exe", "System"],
        "allowed_patterns": ["TEST_*", "TEMP_*"],
        "require_own_process": True,
    }


@pytest.fixture
def empty_constraints() -> dict:
    """Provide an empty constraints dictionary."""
    return {}


@pytest.fixture
def none_constraints() -> None:
    """Provide None as constraints."""
    return None
