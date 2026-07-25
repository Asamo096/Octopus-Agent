"""Tests for octopus.tools.filesystem — read, write, edit, glob, grep."""

from __future__ import annotations

from pathlib import Path

import pytest

from octopus.core.kernel import Context, Kernel, PermissionMode
from octopus.tools.filesystem import (
    EditFileTool,
    GlobTool,
    GrepTool,
    ReadFileTool,
    WriteFileTool,
)


@pytest.fixture
def ctx(kernel: Kernel, tmp_path: Path) -> Context:
    return Context(
        session_id="test",
        kernel=kernel,
        workspace=tmp_path,
        permission_mode=PermissionMode.FULL_AUTO,
    )


class TestReadFileTool:
    async def test_read_existing_file(self, ctx: Context, tmp_path: Path) -> None:
        (tmp_path / "test.py").write_text("hello\nworld\n")
        tool = ReadFileTool()
        result = await tool.execute({"path": "test.py"}, ctx)
        assert result.success
        assert "hello" in result.output

    async def test_read_nonexistent(self, ctx: Context) -> None:
        tool = ReadFileTool()
        result = await tool.execute({"path": "nope.txt"}, ctx)
        assert not result.success
        assert "not found" in (result.error or "").lower()

    async def test_read_with_offset_limit(self, ctx: Context, tmp_path: Path) -> None:
        (tmp_path / "lines.txt").write_text("a\nb\nc\nd\ne\n")
        tool = ReadFileTool()
        result = await tool.execute({"path": "lines.txt", "offset": 1, "limit": 2}, ctx)
        assert result.success
        lines = result.output.strip().split("\n")
        assert lines == ["b", "c"]


class TestWriteFileTool:
    async def test_write_creates_file(self, ctx: Context, tmp_path: Path) -> None:
        tool = WriteFileTool()
        result = await tool.execute({"path": "out.txt", "content": "hello"}, ctx)
        assert result.success
        assert (tmp_path / "out.txt").read_text() == "hello"

    async def test_write_creates_dirs(self, ctx: Context, tmp_path: Path) -> None:
        tool = WriteFileTool()
        result = await tool.execute(
            {"path": "sub/dir/file.txt", "content": "deep"}, ctx
        )
        assert result.success
        assert (tmp_path / "sub" / "dir" / "file.txt").read_text() == "deep"

    async def test_write_overwrites(self, ctx: Context, tmp_path: Path) -> None:
        (tmp_path / "f.txt").write_text("old")
        tool = WriteFileTool()
        result = await tool.execute({"path": "f.txt", "content": "new"}, ctx)
        assert result.success
        assert (tmp_path / "f.txt").read_text() == "new"


class TestEditFileTool:
    async def test_edit_single_occurrence(self, ctx: Context, tmp_path: Path) -> None:
        (tmp_path / "f.py").write_text("def foo():\n    pass\n")
        tool = EditFileTool()
        result = await tool.execute(
            {"path": "f.py", "old_string": "pass", "new_string": "return 42"},
            ctx,
        )
        assert result.success
        assert "return 42" in (tmp_path / "f.py").read_text()

    async def test_edit_not_found(self, ctx: Context, tmp_path: Path) -> None:
        (tmp_path / "f.py").write_text("hello")
        tool = EditFileTool()
        result = await tool.execute(
            {"path": "f.py", "old_string": "xyz", "new_string": "abc"},
            ctx,
        )
        assert not result.success
        assert "not found" in (result.error or "").lower()

    async def test_edit_multiple_occurrences_fails(
        self, ctx: Context, tmp_path: Path
    ) -> None:
        (tmp_path / "f.py").write_text("aaa\naaa\n")
        tool = EditFileTool()
        result = await tool.execute(
            {"path": "f.py", "old_string": "aaa", "new_string": "bbb"},
            ctx,
        )
        assert not result.success
        assert "2 times" in (result.error or "")

    async def test_edit_nonexistent_file(self, ctx: Context) -> None:
        tool = EditFileTool()
        result = await tool.execute(
            {"path": "nope.py", "old_string": "a", "new_string": "b"},
            ctx,
        )
        assert not result.success


class TestGlobTool:
    async def test_glob_finds_files(self, ctx: Context, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("")
        (tmp_path / "b.py").write_text("")
        (tmp_path / "c.txt").write_text("")
        tool = GlobTool()
        result = await tool.execute({"pattern": "*.py"}, ctx)
        assert result.success
        assert "a.py" in result.output
        assert "b.py" in result.output
        assert "c.txt" not in result.output

    async def test_glob_recursive(self, ctx: Context, tmp_path: Path) -> None:
        (tmp_path / "sub" / "deep.py").parent.mkdir()
        (tmp_path / "sub" / "deep.py").write_text("")
        tool = GlobTool()
        result = await tool.execute({"pattern": "**/*.py"}, ctx)
        assert result.success
        assert "deep.py" in result.output

    async def test_glob_no_matches(self, ctx: Context) -> None:
        tool = GlobTool()
        result = await tool.execute({"pattern": "*.nonexistent"}, ctx)
        assert result.success
        assert "no files" in result.output.lower()


class TestGrepTool:
    async def test_grep_finds_matches(self, ctx: Context, tmp_path: Path) -> None:
        (tmp_path / "f.py").write_text("def foo():\n    pass\n")
        tool = GrepTool()
        result = await tool.execute({"pattern": "def foo"}, ctx)
        assert result.success
        assert "def foo" in result.output

    async def test_grep_no_matches(self, ctx: Context, tmp_path: Path) -> None:
        (tmp_path / "f.py").write_text("hello\n")
        tool = GrepTool()
        result = await tool.execute({"pattern": "xyz"}, ctx)
        assert result.success
        assert "no matches" in result.output.lower()

    async def test_grep_invalid_regex(self, ctx: Context) -> None:
        tool = GrepTool()
        result = await tool.execute({"pattern": "[invalid"}, ctx)
        assert not result.success
        assert "invalid regex" in (result.error or "").lower()

    async def test_grep_with_include(self, ctx: Context, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("import os\n")
        (tmp_path / "b.txt").write_text("import os\n")
        tool = GrepTool()
        result = await tool.execute({"pattern": "import", "include": "*.py"}, ctx)
        assert result.success
        assert "a.py" in result.output
        assert "b.txt" not in result.output
