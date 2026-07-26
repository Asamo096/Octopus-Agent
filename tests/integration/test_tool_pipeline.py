"""Integration tests for tool execution pipeline.

Tests tool execution through the harness kernel: permission checks,
audit logging, sandbox validation, and rollback checkpoints.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from octopus.core.kernel import Context, Kernel, PermissionMode, ToolCall
from octopus.tools.base import ToolRegistry
from octopus.tools.filesystem import register_filesystem_tools
from octopus.tools.shell import register_shell_tool


@pytest.fixture
async def test_kernel(tmp_path: Path) -> Kernel:
    db_path = tmp_path / "test_tool_pipeline.db"
    k = Kernel(
        db_path=db_path,
        workspace=tmp_path,
        permission_mode=PermissionMode.FULL_AUTO,
    )
    await k.initialize()
    yield k
    await k.shutdown()


@pytest.fixture
def registry(test_kernel: Kernel) -> ToolRegistry:
    reg = ToolRegistry()
    register_filesystem_tools(reg, test_kernel)
    register_shell_tool(reg, test_kernel)
    return reg


@pytest.fixture
def ctx(test_kernel: Kernel, tmp_path: Path) -> Context:
    return Context(
        session_id="test-tools",
        kernel=test_kernel,
        workspace=tmp_path,
        permission_mode=PermissionMode.FULL_AUTO,
    )


# ---------------------------------------------------------------------------
# Read file tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_file_through_kernel(
    test_kernel: Kernel, registry: ToolRegistry, ctx: Context, tmp_path: Path
) -> None:
    """read_file tool passes through the full harness pipeline."""
    test_file = tmp_path / "test_read.txt"
    test_file.write_text("hello world")

    tool = registry.get("read_file")
    assert tool is not None

    result = await test_kernel.execute_tool(
        ToolCall(tool_name="read_file", arguments={"path": str(test_file)}),
        ctx,
    )
    assert result.success
    assert "hello world" in str(result.output)


@pytest.mark.asyncio
async def test_write_file_through_kernel(
    test_kernel: Kernel, registry: ToolRegistry, ctx: Context, tmp_path: Path
) -> None:
    """write_file tool passes through the full harness pipeline."""
    test_file = tmp_path / "test_write.txt"

    tool = registry.get("write_file")
    assert tool is not None

    result = await test_kernel.execute_tool(
        ToolCall(
            tool_name="write_file",
            arguments={"path": str(test_file), "content": "new content"},
        ),
        ctx,
    )
    assert result.success
    assert test_file.exists()
    assert test_file.read_text() == "new content"


@pytest.mark.asyncio
async def test_safe_shell_command(
    test_kernel: Kernel, registry: ToolRegistry, ctx: Context
) -> None:
    """Safe commands (ls, echo) execute without issues."""
    tool = registry.get("shell")
    assert tool is not None

    result = await test_kernel.execute_tool(
        ToolCall(tool_name="shell", arguments={"command": "echo hello"}),
        ctx,
    )
    assert result.success
    assert "hello" in str(result.output)


# ---------------------------------------------------------------------------
# Audit log tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_log_entry_created(
    test_kernel: Kernel, registry: ToolRegistry, ctx: Context, tmp_path: Path
) -> None:
    """Every tool execution is logged to the audit trail."""
    test_file = tmp_path / "audit_test.txt"
    test_file.write_text("audit content")

    await test_kernel.execute_tool(
        ToolCall(tool_name="read_file", arguments={"path": str(test_file)}),
        ctx,
    )

    events = await test_kernel.audit.query()
    assert len(events) > 0
    read_events = [e for e in events if e.tool == "read_file"]
    assert len(read_events) > 0


# ---------------------------------------------------------------------------
# Tool registry tests
# ---------------------------------------------------------------------------


def test_all_tools_registered(registry: ToolRegistry) -> None:
    """All expected tools are registered."""
    tool_names = registry.list_names()
    assert "read_file" in tool_names
    assert "write_file" in tool_names
    assert "shell" in tool_names


def test_tool_schema_generation(registry: ToolRegistry) -> None:
    """Each tool generates valid OpenAI tool schemas."""
    for name in registry.list_names():
        tool = registry.get(name)
        if tool is not None:
            # Check tool has required attributes
            assert tool.name
            assert tool.description
            assert tool.input_schema is not None


def test_get_nonexistent_tool(registry: ToolRegistry) -> None:
    """Getting a tool that doesn't exist returns None."""
    assert registry.get("nonexistent_tool_xyz") is None
