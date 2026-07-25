"""Tests for octopus.tools.git — GitTool."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from octopus.core.kernel import Context, Kernel, PermissionMode
from octopus.tools.git import GitTool


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a temporary git repository."""
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    # Create initial commit
    (tmp_path / "README.md").write_text("# Test\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True, check=True
    )
    return tmp_path


@pytest.fixture
def ctx(kernel: Kernel, git_repo: Path) -> Context:
    return Context(
        session_id="test",
        kernel=kernel,
        workspace=git_repo,
        permission_mode=PermissionMode.FULL_AUTO,
    )


class TestGitTool:
    async def test_status(self, ctx: Context) -> None:
        tool = GitTool()
        result = await tool.execute({"action": "status"}, ctx)
        assert result.success
        assert "main" in result.output or "master" in result.output

    async def test_log(self, ctx: Context) -> None:
        tool = GitTool()
        result = await tool.execute({"action": "log", "--oneline": ""}, ctx)
        assert result.success
        assert "init" in result.output

    async def test_diff(self, ctx: Context, git_repo: Path) -> None:
        # Make a change
        (git_repo / "new_file.txt").write_text("hello")
        tool = GitTool()
        result = await tool.execute({"action": "diff"}, ctx)
        assert result.success

    async def test_add_and_commit(self, ctx: Context, git_repo: Path) -> None:
        (git_repo / "file.txt").write_text("content")
        tool = GitTool()

        # Add
        result = await tool.execute({"action": "add", "args": "."}, ctx)
        assert result.success

        # Commit
        result = await tool.execute({"action": "commit", "message": "add file"}, ctx)
        assert result.success

    async def test_commit_requires_message(self, ctx: Context) -> None:
        tool = GitTool()
        result = await tool.execute({"action": "commit"}, ctx)
        assert not result.success
        assert "message" in (result.error or "").lower()

    async def test_invalid_action(self, ctx: Context) -> None:
        tool = GitTool()
        result = await tool.execute({"action": "push"}, ctx)
        assert not result.success
        assert "not allowed" in (result.error or "").lower()
