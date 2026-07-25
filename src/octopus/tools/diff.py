"""Diff tool — generate structured diffs for GUI preview."""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from octopus.core.kernel import Context, ToolResult


class DiffTool:
    """Generate unified diffs between file versions."""

    name = "diff"
    description = (
        "Generate a unified diff between two files, or between a file and its "
        "original content. Useful for previewing changes before applying them."
    )
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path to diff",
            },
            "old_content": {
                "type": "string",
                "description": "Original content (if comparing against provided text)",
            },
            "new_content": {
                "type": "string",
                "description": "New content (if comparing against provided text)",
            },
            "context_lines": {
                "type": "integer",
                "description": "Number of context lines around changes (default: 3)",
                "default": 3,
            },
        },
        "required": [],
    }

    async def execute(self, args: dict[str, Any], ctx: Context) -> ToolResult:
        path = args.get("path")
        old_content = args.get("old_content")
        new_content = args.get("new_content")
        context_lines = args.get("context_lines", 3)

        # Mode 1: Compare file against provided content
        if path and (old_content is not None or new_content is not None):
            file_path = _resolve_path(path, ctx)
            if not file_path.exists():
                if old_content is None:
                    return ToolResult(
                        success=False,
                        output=None,
                        error=f"File not found: {file_path}",
                    )
                # File doesn't exist yet — treat as new file
                old_lines = (old_content or "").splitlines(keepends=True)
                new_lines = (new_content or "").splitlines(keepends=True)
            else:
                file_content = file_path.read_text(encoding="utf-8", errors="replace")
                old_lines = (old_content or file_content).splitlines(keepends=True)
                new_lines = (new_content or file_content).splitlines(keepends=True)

        # Mode 2: Compare two provided contents
        elif old_content is not None and new_content is not None:
            old_lines = old_content.splitlines(keepends=True)
            new_lines = new_content.splitlines(keepends=True)

        else:
            return ToolResult(
                success=False,
                output=None,
                error="Provide either 'path' with 'old_content'/'new_content', or both 'old_content' and 'new_content'.",
            )

        # Generate unified diff
        diff_lines = list(
            difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"a/{path}" if path else "original",
                tofile=f"b/{path}" if path else "modified",
                n=context_lines,
            )
        )

        if not diff_lines:
            return ToolResult(success=True, output="No differences found.")

        diff_text = "".join(diff_lines)

        # Count changes
        additions = sum(
            1
            for line in diff_lines
            if line.startswith("+") and not line.startswith("+++")
        )
        deletions = sum(
            1
            for line in diff_lines
            if line.startswith("-") and not line.startswith("---")
        )

        return ToolResult(
            success=True,
            output=diff_text,
            metadata={
                "additions": additions,
                "deletions": deletions,
                "path": path,
            },
        )


class GitDiffTool:
    """Show git diff for the working directory or specific files."""

    name = "git_diff"
    description = "Show git diff for unstaged changes. Optionally filter by file path."
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path to diff (optional, defaults to all changes)",
            },
            "cached": {
                "type": "boolean",
                "description": "Show staged changes instead of unstaged (default: false)",
                "default": False,
            },
        },
    }

    async def execute(self, args: dict[str, Any], ctx: Context) -> ToolResult:
        import asyncio

        path = args.get("path")
        cached = args.get("cached", False)

        cmd = ["git", "diff"]
        if cached:
            cmd.append("--cached")
        if path:
            cmd.append(path)

        cwd = str(ctx.workspace) if ctx.workspace else None
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

            output = stdout.decode("utf-8", errors="replace").strip() if stdout else ""
            if not output:
                return ToolResult(success=True, output="No changes.")

            return ToolResult(success=True, output=output)
        except Exception as e:
            return ToolResult(success=False, output=None, error=str(e))


def _resolve_path(raw: str, ctx: Context) -> Path:
    """Resolve a path relative to the workspace."""
    p = Path(raw).expanduser()
    if p.is_absolute():
        return p
    base = ctx.workspace or Path.cwd()
    return (base / p).resolve()


def register_diff_tools(registry: Any, kernel: Any) -> None:
    """Register diff tools."""
    for tool_cls in [DiffTool, GitDiffTool]:
        tool = tool_cls()
        registry.register(tool)
        kernel.register_tool(tool)
