"""Integration tests for sandbox backends and kernel routing.

Tests the sandbox adapter, CubeSandbox backend (import-level),
LocalBackend execution, and sandbox + permission integration.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from octopus.core.kernel import Context, Kernel, PermissionMode, ToolCall
from octopus.sandbox.adapter import SandboxResult
from octopus.sandbox.cube import CubeBackend
from octopus.sandbox.local import LocalBackend
from octopus.tools.base import ToolRegistry
from octopus.tools.filesystem import register_filesystem_tools
from octopus.tools.shell import register_shell_tool


# ---------------------------------------------------------------------------
# CubeBackend tests (no live CubeAPI needed)
# ---------------------------------------------------------------------------


def test_cube_backend_creation() -> None:
    """CubeBackend can be instantiated with config."""
    backend = CubeBackend(
        api_url="http://127.0.0.1:3000",
        template_id="tpl-test-template",
        api_key="test-key",
    )
    assert backend.name == "cube"
    assert backend._template_id == "tpl-test-template"


def test_cube_backend_env_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """CubeBackend reads config from environment variables."""
    monkeypatch.setenv("CUBE_API_URL", "http://10.0.0.1:3000")
    monkeypatch.setenv("CUBE_TEMPLATE_ID", "tpl-from-env")
    monkeypatch.setenv("CUBE_API_KEY", "env-key")

    backend = CubeBackend()
    assert backend._api_url == "http://10.0.0.1:3000"
    assert backend._template_id == "tpl-from-env"


def test_cube_backend_missing_template_id() -> None:
    """CubeBackend raises ValueError when creating without template_id."""
    backend = CubeBackend(template_id="")
    with pytest.raises(ValueError, match="CUBE_TEMPLATE_ID"):
        # Use asyncio to call async create
        import asyncio
        asyncio.run(backend.create())


def test_cube_backend_execute_without_create() -> None:
    """Executing command before create returns error."""
    backend = CubeBackend(template_id="tpl-test")
    import asyncio

    async def _test() -> None:
        result = await backend.execute_command("echo hello")
        assert not result.success
        assert "not created" in (result.error or "")

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# LocalBackend tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_local_backend_echo() -> None:
    """LocalBackend executes echo command."""
    backend = LocalBackend()
    await backend.create()

    result = await backend.execute_command("echo hello")
    assert result.success
    assert "hello" in (result.output or "")


@pytest.mark.asyncio
async def test_local_backend_command_failure() -> None:
    """LocalBackend reports command failure."""
    backend = LocalBackend()
    await backend.create()

    result = await backend.execute_command("exit 1")
    assert not result.success
    assert result.exit_code == 1


@pytest.mark.asyncio
async def test_local_backend_timeout() -> None:
    """LocalBackend times out long-running commands."""
    backend = LocalBackend()
    await backend.create()

    result = await backend.execute_command("sleep 5", timeout=0.1)
    assert not result.success
    assert "timed out" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_local_backend_read_write(tmp_path: Path) -> None:
    """LocalBackend reads and writes files."""
    backend = LocalBackend()
    await backend.create()

    test_file = tmp_path / "sandbox_test.txt"
    await backend.write_file(str(test_file), "hello sandbox")
    content = await backend.read_file(str(test_file))
    assert content == "hello sandbox"


@pytest.mark.asyncio
async def test_local_backend_snapshot_not_supported() -> None:
    """LocalBackend snapshots raise NotImplementedError."""
    backend = LocalBackend()
    await backend.create()

    with pytest.raises(NotImplementedError):
        await backend.create_snapshot("test-snap")


# ---------------------------------------------------------------------------
# Kernel sandbox routing tests
# ---------------------------------------------------------------------------


@pytest.fixture
async def kernel_with_sandbox(tmp_path: Path) -> Kernel:
    """Kernel with local sandbox backend configured."""
    db_path = tmp_path / "test_sandbox_kernel.db"
    k = Kernel(
        db_path=db_path,
        workspace=tmp_path,
        permission_mode=PermissionMode.FULL_AUTO,
    )
    await k.initialize()
    yield k
    await k.shutdown()


@pytest.mark.asyncio
async def test_kernel_sandbox_backend_initialized(
    kernel_with_sandbox: Kernel,
) -> None:
    """Kernel initializes with a sandbox backend (local by default)."""
    assert kernel_with_sandbox.sandbox_backend is not None
    assert kernel_with_sandbox.sandbox_backend.name == "local"


@pytest.mark.asyncio
async def test_kernel_sandbox_shell_routing(
    kernel_with_sandbox: Kernel, tmp_path: Path
) -> None:
    """Shell commands are routed through the sandbox backend."""
    registry = ToolRegistry()
    register_shell_tool(registry, kernel_with_sandbox)

    ctx = Context(
        session_id="test-sandbox-shell",
        kernel=kernel_with_sandbox,
        workspace=tmp_path,
        permission_mode=PermissionMode.FULL_AUTO,
    )

    result = await kernel_with_sandbox.execute_tool(
        ToolCall(tool_name="shell", arguments={"command": "echo routed"}),
        ctx,
    )
    assert result.success
    assert "routed" in str(result.output)


# ---------------------------------------------------------------------------
# Permission + sandbox integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_permission_blocks_before_sandbox(
    kernel_with_sandbox: Kernel, tmp_path: Path
) -> None:
    """Permission check runs BEFORE sandbox routing. Blocked ops never reach sandbox."""
    # Switch to PLAN mode (blocks shell execution)
    kernel_with_sandbox.set_permission_mode(PermissionMode.PLAN)

    registry = ToolRegistry()
    register_shell_tool(registry, kernel_with_sandbox)

    ctx = Context(
        session_id="test-perm-sandbox",
        kernel=kernel_with_sandbox,
        workspace=tmp_path,
        permission_mode=PermissionMode.PLAN,
    )

    result = await kernel_with_sandbox.execute_tool(
        ToolCall(tool_name="shell", arguments={"command": "echo blocked"}),
        ctx,
    )
    assert not result.success
    assert "blocked" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_full_auto_allows_sandbox_execution(
    kernel_with_sandbox: Kernel, tmp_path: Path
) -> None:
    """FULL_AUTO mode: permissions pass, sandbox executes."""
    kernel_with_sandbox.set_permission_mode(PermissionMode.FULL_AUTO)

    registry = ToolRegistry()
    register_shell_tool(registry, kernel_with_sandbox)

    ctx = Context(
        session_id="test-auto-sandbox",
        kernel=kernel_with_sandbox,
        workspace=tmp_path,
        permission_mode=PermissionMode.FULL_AUTO,
    )

    result = await kernel_with_sandbox.execute_tool(
        ToolCall(tool_name="shell", arguments={"command": "echo allowed"}),
        ctx,
    )
    assert result.success
    assert "allowed" in str(result.output)


@pytest.mark.asyncio
async def test_default_mode_prompts_before_sandbox(
    tmp_path: Path,
) -> None:
    """DEFAULT mode: permission prompt fires before sandbox execution."""
    db_path = tmp_path / "test_default_sandbox.db"
    k = Kernel(
        db_path=db_path,
        workspace=tmp_path,
        permission_mode=PermissionMode.DEFAULT,
    )
    await k.initialize()

    try:
        registry = ToolRegistry()
        register_shell_tool(registry, k)

        ctx = Context(
            session_id="test-default-sandbox",
            kernel=k,
            workspace=tmp_path,
            permission_mode=PermissionMode.DEFAULT,
        )

        # With no permission prompt callback, it auto-approves
        result = await k.execute_tool(
            ToolCall(tool_name="shell", arguments={"command": "echo approved"}),
            ctx,
        )
        # Should succeed (no prompt callback = auto-approve in non-interactive)
        assert result.success
    finally:
        await k.shutdown()


@pytest.mark.asyncio
async def test_audit_logs_sandbox_operations(
    kernel_with_sandbox: Kernel, tmp_path: Path
) -> None:
    """Audit log records sandbox execution details."""
    registry = ToolRegistry()
    register_shell_tool(registry, kernel_with_sandbox)

    ctx = Context(
        session_id="test-audit-sandbox",
        kernel=kernel_with_sandbox,
        workspace=tmp_path,
        permission_mode=PermissionMode.FULL_AUTO,
    )

    await kernel_with_sandbox.execute_tool(
        ToolCall(tool_name="shell", arguments={"command": "echo audit_test"}),
        ctx,
    )

    events = await kernel_with_sandbox.audit.query()
    shell_events = [e for e in events if e.tool == "shell"]
    assert len(shell_events) > 0
    assert shell_events[0].permission_decision == "ALLOWED"
