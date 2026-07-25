"""Tests for octopus.tools.diff — DiffTool and GitDiffTool."""

from __future__ import annotations

from pathlib import Path

import pytest

from octopus.core.kernel import Context, Kernel, PermissionMode
from octopus.tools.diff import DiffTool, GitDiffTool


@pytest.fixture
def ctx(kernel: Kernel, tmp_path: Path) -> Context:
    return Context(
        session_id="test",
        kernel=kernel,
        workspace=tmp_path,
        permission_mode=PermissionMode.FULL_AUTO,
    )


class TestDiffTool:
    async def test_diff_two_contents(self, ctx: Context) -> None:
        tool = DiffTool()
        result = await tool.execute(
            {"old_content": "hello\n", "new_content": "world\n"},
            ctx,
        )
        assert result.success
        assert "-hello" in result.output
        assert "+world" in result.output

    async def test_diff_no_changes(self, ctx: Context) -> None:
        tool = DiffTool()
        result = await tool.execute(
            {"old_content": "same\n", "new_content": "same\n"},
            ctx,
        )
        assert result.success
        assert "no differences" in result.output.lower()

    async def test_diff_file_against_content(
        self, ctx: Context, tmp_path: Path
    ) -> None:
        (tmp_path / "f.txt").write_text("old content\n")
        tool = DiffTool()
        result = await tool.execute(
            {
                "path": "f.txt",
                "old_content": "old content\n",
                "new_content": "new content\n",
            },
            ctx,
        )
        assert result.success
        assert "-old content" in result.output
        assert "+new content" in result.output
        assert result.metadata is not None
        assert result.metadata["additions"] >= 1
        assert result.metadata["deletions"] >= 1

    async def test_diff_missing_args(self, ctx: Context) -> None:
        tool = DiffTool()
        result = await tool.execute({}, ctx)
        assert not result.success


class TestGitDiffTool:
    async def test_git_diff_no_changes(self, ctx: Context, tmp_path: Path) -> None:
        # No git repo — should still work or return error gracefully
        tool = GitDiffTool()
        result = await tool.execute({}, ctx)
        # May succeed with "no changes" or fail if not a git repo
        assert (
            result.success
            or "not a git" in (result.error or "").lower()
            or "fatal" in (result.error or "").lower()
        )
