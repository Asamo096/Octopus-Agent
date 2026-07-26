"""Git tool — git operations through the harness governance pipeline."""

from __future__ import annotations

import asyncio
from typing import Any

from octopus.core.kernel import Context, ToolResult


class GitTool:
    """Execute git commands."""

    name = "git"
    description = (
        "Execute git commands. Supported actions: status, diff, log, add, commit, "
        "checkout, branch, restore, show."
    )
    is_destructive = True
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Git action to perform",
                "enum": [
                    "status",
                    "diff",
                    "log",
                    "add",
                    "commit",
                    "checkout",
                    "branch",
                    "restore",
                    "show",
                ],
            },
            "args": {
                "type": "string",
                "description": "Additional arguments for the git command",
                "default": "",
            },
            "message": {
                "type": "string",
                "description": "Commit message (required for 'commit' action)",
            },
        },
        "required": ["action"],
    }

    # Allowed git subcommands (safety whitelist)
    ALLOWED_ACTIONS = frozenset(
        {
            "status",
            "diff",
            "log",
            "add",
            "commit",
            "checkout",
            "branch",
            "restore",
            "show",
            "remote",
            "stash",
        }
    )

    async def execute(self, args: dict[str, Any], ctx: Context) -> ToolResult:
        action = args["action"]
        extra_args = args.get("args", "")
        message = args.get("message", "")

        if action not in self.ALLOWED_ACTIONS:
            return ToolResult(
                success=False,
                output=None,
                error=f"Git action '{action}' is not allowed. Allowed: {', '.join(sorted(self.ALLOWED_ACTIONS))}",
            )

        # Build the git command
        cmd_parts = ["git", action]

        # Special handling for commit
        if action == "commit":
            if not message:
                return ToolResult(
                    success=False,
                    output=None,
                    error="Commit message is required for 'commit' action.",
                )
            cmd_parts.extend(["-m", message])

        # Add extra arguments
        if extra_args:
            cmd_parts.extend(extra_args.split())

        # Execute
        cwd = str(ctx.workspace) if ctx.workspace else None
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd_parts,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=30
            )

            stdout = (
                stdout_bytes.decode("utf-8", errors="replace").strip()
                if stdout_bytes
                else ""
            )
            stderr = (
                stderr_bytes.decode("utf-8", errors="replace").strip()
                if stderr_bytes
                else ""
            )

            success = proc.returncode == 0
            output_parts: list[str] = []
            if stdout:
                output_parts.append(stdout)
            if stderr and not success:
                output_parts.append(f"[stderr]\n{stderr}")

            return ToolResult(
                success=success,
                output="\n".join(output_parts) if output_parts else "(no output)",
                error=None if success else f"git exited with code {proc.returncode}",
                metadata={"exit_code": proc.returncode, "action": action},
            )
        except TimeoutError:
            return ToolResult(
                success=False, output=None, error="Git command timed out (30s)"
            )
        except Exception as e:
            return ToolResult(success=False, output=None, error=str(e))


def register_git_tool(registry: Any, kernel: Any) -> None:
    """Register the git tool."""
    tool = GitTool()
    registry.register(tool)
    kernel.register_tool(tool)
