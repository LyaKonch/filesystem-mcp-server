"""Executable usage scenarios that serve as living project documentation.

These tests intentionally read like user workflows for MCP tools.
They are designed to explain how the server components behave in practice.
"""

from pathlib import Path

import pytest

from config import settings
from tools.filesystem import (
    create_directory,
    filesystem_summary,
    list_files,
    read_multiple_files,
    search_files,
    write_file,
)
from tools.monitoring import get_disk_status, get_system_info, get_system_resource_usage
from tools.server_management import add_allowed_root, list_allowed_roots, remove_root


class DummySession:
    """Minimal session stub for tests without MCP client capabilities."""

    def check_client_capability(self, _capability) -> bool:
        """Report that optional capabilities are disabled in test context."""
        return False


class DummyContext:
    """Minimal FastMCP-like context used by tool functions in tests."""

    def __init__(self) -> None:
        """Initialize context with a capability-free session stub."""
        self.session = DummySession()

    async def info(self, _message: str) -> None:
        """Compatibility method for tools that may log informational events."""


@pytest.fixture
def ctx() -> DummyContext:
    """Provide a reusable context stub for async tool calls."""
    return DummyContext()


@pytest.fixture
def isolated_allowed_roots() -> list[Path]:
    """Isolate and restore global allowed roots around each test."""
    previous_roots = list(settings.ALLOWED_ROOTS)
    settings.ALLOWED_ROOTS.clear()
    try:
        yield settings.ALLOWED_ROOTS
    finally:
        settings.ALLOWED_ROOTS.clear()
        settings.ALLOWED_ROOTS.extend(previous_roots)


@pytest.mark.asyncio
async def test_filesystem_tools_end_to_end_workflow(
    tmp_path: Path, ctx: DummyContext, isolated_allowed_roots: list[Path]
) -> None:
    """Demonstrate a full file workflow: create, write, discover, read, and summarize.

    Scenario:
        1. Configure one temporary directory as an allowed root.
        2. Create a nested working directory using MCP tool API.
        3. Write text files through the server tool.
        4. Discover files with listing and glob search.
        5. Read multiple files and get filesystem summary statistics.
    """
    isolated_allowed_roots.append(tmp_path)

    workspace_dir = tmp_path / "workspace"
    notes_dir = workspace_dir / "notes"
    alpha_file = notes_dir / "alpha.txt"
    beta_file = notes_dir / "beta.md"

    create_result = await create_directory(str(notes_dir), ctx)
    assert "Created directory" in create_result

    write_alpha_result = await write_file(str(alpha_file), "hello from alpha", ctx)
    write_beta_result = await write_file(str(beta_file), "# beta report", ctx)
    assert "Saved to" in write_alpha_result
    assert "Saved to" in write_beta_result

    listing_output = await list_files(str(notes_dir), ctx)
    assert "alpha.txt" in listing_output
    assert "beta.md" in listing_output

    search_output = await search_files(str(workspace_dir), "**/*.txt", ctx)
    assert "Found 1 files" in search_output
    assert str(alpha_file) in search_output

    read_many_output = await read_multiple_files([str(alpha_file), str(beta_file)], ctx)
    assert "hello from alpha" in read_many_output
    assert "# beta report" in read_many_output

    summary = await filesystem_summary(str(workspace_dir), ctx)
    assert summary["files"] == 2
    assert summary["directories"] >= 1


@pytest.mark.asyncio
async def test_server_roots_management_workflow(
    tmp_path: Path, ctx: DummyContext, isolated_allowed_roots: list[Path]
) -> None:
    """Demonstrate runtime root-management tools as an operational runbook.

    Scenario:
        1. Start with one baseline allowed root.
        2. Add another root dynamically.
        3. Verify visible roots via status listing tool.
        4. Remove the new root and verify it disappears from the effective list.
    """
    primary_root = tmp_path / "primary"
    secondary_root = tmp_path / "secondary"
    primary_root.mkdir()
    secondary_root.mkdir()

    isolated_allowed_roots.append(primary_root)

    add_result = await add_allowed_root(str(secondary_root), ctx)
    assert "Successfully added" in add_result

    roots_listing_after_add = await list_allowed_roots(ctx)
    assert str(primary_root) in roots_listing_after_add
    assert str(secondary_root) in roots_listing_after_add

    remove_result = await remove_root(str(secondary_root))
    assert "Removed root" in remove_result

    roots_listing_after_remove = await list_allowed_roots(ctx)
    assert str(primary_root) in roots_listing_after_remove
    assert str(secondary_root) not in roots_listing_after_remove


@pytest.mark.asyncio
async def test_monitoring_tools_snapshot_workflow(ctx: DummyContext) -> None:
    """Demonstrate health-check style usage of monitoring tools.

    Scenario:
        1. Capture resource usage (CPU and memory).
        2. Read mounted disk metrics.
        3. Capture static host/runtime information.
    """
    resource_usage = await get_system_resource_usage(ctx)
    assert "cpu_percent" in resource_usage
    assert "memory_used_percent" in resource_usage

    disk_status = await get_disk_status(ctx)
    assert isinstance(disk_status, list)

    system_info = await get_system_info(ctx)
    assert "os" in system_info
    assert "hardware" in system_info
    assert "environment" in system_info
