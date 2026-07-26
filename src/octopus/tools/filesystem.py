"""Filesystem tools — read, write, edit, glob, grep."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from octopus.core.kernel import Context, ToolResult

# ---------------------------------------------------------------------------
# read_file
# ---------------------------------------------------------------------------


class ReadFileTool:
    """Read the contents of a file."""

    name = "read_file"
    description = "Read the contents of a file at the given path."
    is_read_only = True
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute or relative file path"},
            "offset": {
                "type": "integer",
                "description": "Line number to start reading from (0-based)",
                "default": 0,
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of lines to read",
                "default": 2000,
            },
        },
        "required": ["path"],
    }

    async def execute(self, args: dict[str, Any], ctx: Context) -> ToolResult:
        path = _resolve_path(args["path"], ctx)
        offset = args.get("offset", 0)
        limit = args.get("limit", 2000)

        if not path.exists():
            return ToolResult(
                success=False, output=None, error=f"File not found: {path}"
            )

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines(keepends=True)
            selected = lines[offset : offset + limit]
            content = "".join(selected)
            return ToolResult(
                success=True,
                output=content,
                metadata={"total_lines": len(lines), "offset": offset, "limit": limit},
            )
        except Exception as e:
            return ToolResult(success=False, output=None, error=str(e))


# ---------------------------------------------------------------------------
# write_file
# ---------------------------------------------------------------------------


class WriteFileTool:
    """Write content to a file, creating parent directories if needed."""

    name = "write_file"
    description = (
        "Write content to a file. Creates parent directories if they don't exist."
    )
    is_destructive = True
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to write to"},
            "content": {"type": "string", "description": "Content to write"},
        },
        "required": ["path", "content"],
    }

    async def execute(self, args: dict[str, Any], ctx: Context) -> ToolResult:
        path = _resolve_path(args["path"], ctx)
        content = args["content"]

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return ToolResult(
                success=True, output=f"Wrote {len(content)} bytes to {path}"
            )
        except Exception as e:
            return ToolResult(success=False, output=None, error=str(e))


# ---------------------------------------------------------------------------
# edit_file
# ---------------------------------------------------------------------------


class EditFileTool:
    """Replace text in a file using exact string matching."""

    name = "edit_file"
    description = "Replace text in a file. Uses exact string matching — old_string must appear exactly once."
    is_destructive = True
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path"},
            "old_string": {"type": "string", "description": "Exact text to replace"},
            "new_string": {"type": "string", "description": "Replacement text"},
        },
        "required": ["path", "old_string", "new_string"],
    }

    async def execute(self, args: dict[str, Any], ctx: Context) -> ToolResult:
        path = _resolve_path(args["path"], ctx)
        old_string = args["old_string"]
        new_string = args["new_string"]

        if not path.exists():
            return ToolResult(
                success=False, output=None, error=f"File not found: {path}"
            )

        try:
            text = path.read_text(encoding="utf-8")
            count = text.count(old_string)
            if count == 0:
                return ToolResult(
                    success=False,
                    output=None,
                    error="old_string not found in file",
                )
            if count > 1:
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"old_string found {count} times — must be unique",
                )
            new_text = text.replace(old_string, new_string, 1)
            path.write_text(new_text, encoding="utf-8")
            return ToolResult(
                success=True,
                output=f"Replaced 1 occurrence in {path}",
                metadata={
                    "old_string": old_string,
                    "new_string": new_string,
                    "file_path": str(path),
                },
            )
        except Exception as e:
            return ToolResult(success=False, output=None, error=str(e))


# ---------------------------------------------------------------------------
# glob
# ---------------------------------------------------------------------------


class GlobTool:
    """Find files matching a glob pattern."""

    name = "glob"
    description = "Find files matching a glob pattern (e.g. '**/*.py', 'src/**/*.ts')."
    is_read_only = True
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Glob pattern"},
            "path": {
                "type": "string",
                "description": "Directory to search in (default: workspace root)",
                "default": ".",
            },
        },
        "required": ["pattern"],
    }

    async def execute(self, args: dict[str, Any], ctx: Context) -> ToolResult:
        pattern = args["pattern"]
        base = _resolve_path(args.get("path", "."), ctx)

        try:
            matches = sorted(
                str(p.relative_to(base)) for p in base.glob(pattern) if p.is_file()
            )
            if not matches:
                return ToolResult(success=True, output="No files found.")
            output = "\n".join(matches)
            return ToolResult(
                success=True,
                output=output,
                metadata={"count": len(matches)},
            )
        except Exception as e:
            return ToolResult(success=False, output=None, error=str(e))


# ---------------------------------------------------------------------------
# grep
# ---------------------------------------------------------------------------


class GrepTool:
    """Search for a regex pattern in files."""

    name = "grep"
    description = "Search for a regex pattern in files under a directory. Returns matching lines with file paths and line numbers."
    is_read_only = True
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Regex pattern to search for"},
            "path": {
                "type": "string",
                "description": "Directory to search in (default: workspace root)",
                "default": ".",
            },
            "include": {
                "type": "string",
                "description": "File glob to filter (e.g. '*.py')",
                "default": "*",
            },
        },
        "required": ["pattern"],
    }

    async def execute(self, args: dict[str, Any], ctx: Context) -> ToolResult:
        pattern = args["pattern"]
        base = _resolve_path(args.get("path", "."), ctx)
        include = args.get("include", "*")

        try:
            regex = re.compile(pattern)
        except re.error as e:
            return ToolResult(success=False, output=None, error=f"Invalid regex: {e}")

        matches: list[str] = []
        try:
            for filepath in sorted(base.rglob(include)):
                if not filepath.is_file():
                    continue
                try:
                    text = filepath.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                for i, line in enumerate(text.splitlines(), 1):
                    if regex.search(line):
                        rel = str(filepath.relative_to(base))
                        matches.append(f"{rel}:{i}: {line.rstrip()}")
                        if len(matches) >= 200:
                            break
                if len(matches) >= 200:
                    break
        except Exception as e:
            return ToolResult(success=False, output=None, error=str(e))

        if not matches:
            return ToolResult(success=True, output="No matches found.")
        return ToolResult(
            success=True,
            output="\n".join(matches),
            metadata={"match_count": len(matches), "truncated": len(matches) >= 200},
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_path(raw: str, ctx: Context) -> Path:
    """Resolve a path relative to the workspace."""
    p = Path(raw).expanduser()
    if p.is_absolute():
        return p
    base = ctx.workspace or Path.cwd()
    return (base / p).resolve()


def register_filesystem_tools(registry: Any, kernel: Any) -> None:
    """Register all filesystem tools with the registry and kernel."""
    tools = [ReadFileTool(), WriteFileTool(), EditFileTool(), GlobTool(), GrepTool()]
    for t in tools:
        registry.register(t)
        kernel.register_tool(t)
