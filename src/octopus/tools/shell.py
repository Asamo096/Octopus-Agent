"""Shell tool — execute shell commands through the harness governance pipeline."""

from __future__ import annotations

import asyncio
from typing import Any

from octopus.core.kernel import Context, ToolResult


class ShellTool:
    """Execute a shell command. Passes through kernel permissions and sandbox."""

    name = "shell"
    description = "Execute a shell command and return stdout/stderr. Dangerous commands require approval."
    is_destructive = True
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute"},
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default: 60)",
                "default": 60,
            },
            "workdir": {
                "type": "string",
                "description": "Working directory (default: workspace)",
                "default": ".",
            },
        },
        "required": ["command"],
    }

    async def execute(self, args: dict[str, Any], ctx: Context) -> ToolResult:
        command = args["command"]
        timeout = args.get("timeout", 60)
        workdir = args.get("workdir", ".")

        # Resolve working directory
        if workdir == ".":
            cwd = str(ctx.workspace) if ctx.workspace else None
        else:
            cwd = str((ctx.workspace / workdir).resolve()) if ctx.workspace else workdir

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except TimeoutError:
                proc.kill()
                await proc.wait()
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Command timed out after {timeout}s",
                    metadata={"exit_code": -1, "command": command},
                )

            stdout = (
                stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
            )
            stderr = (
                stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""
            )

            success = proc.returncode == 0
            output_parts: list[str] = []
            if stdout.strip():
                output_parts.append(stdout.strip())
            if stderr.strip():
                output_parts.append(f"[stderr]\n{stderr.strip()}")

            return ToolResult(
                success=success,
                output="\n".join(output_parts) if output_parts else "(no output)",
                error=None if success else f"Exit code: {proc.returncode}",
                metadata={"exit_code": proc.returncode, "command": command},
            )
        except Exception as e:
            return ToolResult(success=False, output=None, error=str(e))


def register_shell_tool(registry: Any, kernel: Any) -> None:
    """Register the shell tool."""
    tool = ShellTool()
    registry.register(tool)
    kernel.register_tool(tool)
