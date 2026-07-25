"""Tests for octopus.tools.shell — ShellTool."""

from __future__ import annotations

from pathlib import Path

import pytest

from octopus.core.kernel import Context, Kernel, PermissionMode
from octopus.tools.shell import ShellTool


@pytest.fixture
def ctx(kernel: Kernel, tmp_path: Path) -> Context:
    return Context(
        session_id="test",
        kernel=kernel,
        workspace=tmp_path,
        permission_mode=PermissionMode.FULL_AUTO,
    )


class TestShellTool:
    async def test_echo(self, ctx: Context) -> None:
        tool = ShellTool()
        result = await tool.execute({"command": "echo hello"}, ctx)
        assert result.success
        assert "hello" in result.output

    async def test_exit_code_zero(self, ctx: Context) -> None:
        tool = ShellTool()
        result = await tool.execute({"command": "true"}, ctx)
        assert result.success

    async def test_exit_code_nonzero(self, ctx: Context) -> None:
        tool = ShellTool()
        result = await tool.execute({"command": "false"}, ctx)
        assert not result.success
        assert "exit code" in (result.error or "").lower()

    async def test_stderr_captured(self, ctx: Context) -> None:
        tool = ShellTool()
        result = await tool.execute({"command": "echo err >&2"}, ctx)
        assert result.success
        assert "err" in result.output

    async def test_timeout(self, ctx: Context) -> None:
        tool = ShellTool()
        result = await tool.execute({"command": "sleep 10", "timeout": 1}, ctx)
        assert not result.success
        assert "timed out" in (result.error or "").lower()

    async def test_workdir(self, ctx: Context, tmp_path: Path) -> None:
        (tmp_path / "sub").mkdir()
        tool = ShellTool()
        result = await tool.execute({"command": "pwd", "workdir": "sub"}, ctx)
        assert result.success
        assert "sub" in result.output

    async def test_metadata(self, ctx: Context) -> None:
        tool = ShellTool()
        result = await tool.execute({"command": "echo ok"}, ctx)
        assert result.metadata is not None
        assert result.metadata["exit_code"] == 0
