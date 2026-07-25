"""Octopus Agent Kernel — Central orchestrator for harness governance.

Every agent action passes through the Kernel. The pipeline is:
1. PreToolUse hooks (permission check, rollback checkpoint)
2. Permission engine check
3. Sandbox validation (path access, command safety)
4. Tool execution
5. PostToolUse hooks (audit log, result validation)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

# ---------------------------------------------------------------------------
# Core data types
# ---------------------------------------------------------------------------


class PermissionMode(Enum):
    """Permission modes for the kernel."""

    DEFAULT = "default"  # Confirm all operations (manual mode)
    PLAN = "plan"  # Allow write/read/delete, block execution
    ACCEPT_EDITS = "accept_edits"  # Allow write/read/delete, block execution
    FULL_AUTO = "full_auto"  # Allow everything (no permission checks)


@dataclass
class ToolCall:
    """Represents a tool call from the agent."""

    tool_name: str
    arguments: dict[str, Any]
    call_id: str | None = None


@dataclass
class ToolResult:
    """Represents the result of a tool execution."""

    success: bool
    output: Any
    error: str | None = None
    metadata: dict[str, Any] | None = field(default_factory=dict)


@dataclass
class Context:
    """Execution context passed to every tool call.

    Tools access the Kernel through `ctx.kernel` for permission checks,
    audit logging, and other harness operations.
    """

    session_id: str
    kernel: Kernel | None = None
    workspace: Path | None = None
    permission_mode: PermissionMode = PermissionMode.DEFAULT
    user_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Tool protocol
# ---------------------------------------------------------------------------


class Tool(Protocol):
    """Protocol that all tools must implement."""

    name: str
    description: str

    async def execute(self, args: dict[str, Any], ctx: Context) -> ToolResult: ...


# ---------------------------------------------------------------------------
# Kernel
# ---------------------------------------------------------------------------


class Kernel:
    """Central orchestrator.  Every agent action passes through it.

    The Kernel owns:
    - PermissionEngine — path/command allow/deny rules
    - AuditLogger      — structured audit trail (SQLite)
    - Sandbox          — filesystem sandbox isolation
    - HookManager      — PreToolUse / PostToolUse lifecycle hooks
    - StateManager     — global application state (SQLite)
    """

    def __init__(
        self,
        *,
        workspace: Path | None = None,
        permission_mode: PermissionMode = PermissionMode.DEFAULT,
        db_path: Path | None = None,
        settings: dict[str, Any] | None = None,
    ) -> None:
        self.workspace = workspace or Path.cwd()
        self.permission_mode = permission_mode
        self.settings = settings or {}

        # Resolve database path
        self._db_path = db_path or (Path.home() / ".octopus" / "octopus.db")

        # Components — initialized lazily in initialize()
        self.permissions: Any = None
        self.audit: Any = None
        self.sandbox: Any = None
        self.hooks: Any = None
        self.state: Any = None

        # Tool registry (populated externally)
        self._tools: dict[str, Tool] = {}

        # Permission prompt callback — set by CLI to prompt user
        self._permission_prompt: Any = None

        self._initialized = False

    # ---- lifecycle --------------------------------------------------------

    async def initialize(self) -> None:
        """Initialize all harness components."""
        if self._initialized:
            return

        # Import here to avoid circular imports at module level
        from octopus.core.audit import AuditLogger
        from octopus.core.hooks import HookManager, register_default_hooks
        from octopus.core.permissions import PermissionEngine
        from octopus.core.sandbox import Sandbox
        from octopus.core.state import StateManager

        # Ensure parent directory exists
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self.permissions = PermissionEngine(self.settings.get("permissions", {}))
        self.sandbox = Sandbox(self.settings.get("sandbox", {}))
        self.hooks = HookManager()
        self.audit = AuditLogger(db_path=self._db_path)
        self.state = StateManager(db_path=self._db_path)

        register_default_hooks(self.hooks)

        self._initialized = True

    async def shutdown(self) -> None:
        """Shutdown the kernel and release resources."""
        if self.audit is not None:
            await self.audit.close()
        if self.state is not None:
            await self.state.close()
        self._initialized = False

    # ---- tool registry ----------------------------------------------------

    def register_tool(self, tool: Tool) -> None:
        """Register a tool with the kernel."""
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Tool | None:
        """Get a registered tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[dict[str, Any]]:
        """List all registered tools (for provider tool definitions)."""
        return [
            {"name": t.name, "description": t.description} for t in self._tools.values()
        ]

    # ---- harness pipeline -------------------------------------------------

    async def execute_tool(self, tool_call: ToolCall, ctx: Context) -> ToolResult:
        """Execute a tool call through the full harness pipeline.

        Steps:
        1. PreToolUse hooks
        2. Permission check
        3. Sandbox validation
        4. Tool execution
        5. PostToolUse hooks + audit log
        """
        if not self._initialized:
            await self.initialize()

        start_time = time.monotonic()

        # Ensure context references this kernel
        ctx.kernel = self
        if ctx.workspace is None:
            ctx.workspace = self.workspace

        # ---- Step 1: PreToolUse hooks ----
        from octopus.core.hooks import HookEvent

        hook_data: dict[str, Any] = {
            "tool_call": tool_call,
            "context": ctx,
        }
        hook_result = await self.hooks.fire(HookEvent.PRE_TOOL_USE, hook_data)
        if hook_result.blocked:
            return ToolResult(
                success=False,
                output=None,
                error=hook_result.error or "Blocked by PreToolUse hook",
            )
        # Allow hooks to mutate data (e.g. inject rollback checkpoint)
        if hook_result.modified_data:
            hook_data.update(hook_result.modified_data)

        # ---- Step 2: Permission check ----
        perm_result = self.permissions.check(tool_call, ctx)
        if not perm_result.allowed:
            duration = time.monotonic() - start_time
            await self._log_audit(tool_call, ctx, None, duration, "DENIED")
            return ToolResult(
                success=False,
                output=None,
                error=f"Permission denied: {perm_result.reason}",
            )
        # Permission mode logic:
        # - FULL_AUTO: auto-approve everything
        # - DEFAULT (manual): require approval for ALL operations
        # - PLAN/ACCEPT_EDITS: allow write/read/delete, block execution (shell)
        if self.permission_mode == PermissionMode.FULL_AUTO:
            # Auto-approve everything
            pass
        elif self.permission_mode == PermissionMode.DEFAULT:
            # Manual mode: require approval for ALL operations
            if self._permission_prompt is not None:
                approved = await self._permission_prompt(
                    tool_call.tool_name,
                    tool_call.arguments,
                    perm_result.reason or "Approval required",
                )
                if not approved:
                    duration = time.monotonic() - start_time
                    await self._log_audit(tool_call, ctx, None, duration, "USER_DENIED")
                    return ToolResult(
                        success=False,
                        output=None,
                        error="Permission denied by user",
                    )
            # If no prompt callback, auto-approve (for non-interactive mode)
        elif self.permission_mode in (PermissionMode.PLAN, PermissionMode.ACCEPT_EDITS):
            # Accept edits & plan mode: allow write/read/delete, block shell execution
            if tool_call.tool_name == "shell":
                duration = time.monotonic() - start_time
                await self._log_audit(tool_call, ctx, None, duration, "EXECUTION_BLOCKED")
                return ToolResult(
                    success=False,
                    output=None,
                    error="Shell execution blocked in this mode. Switch to manual or auto mode.",
                )

        # ---- Step 3: Sandbox validation ----
        if tool_call.tool_name in ("write_file", "edit_file", "shell"):
            sandbox_ok, sandbox_reason = self._sandbox_check(tool_call, ctx)
            if not sandbox_ok:
                duration = time.monotonic() - start_time
                await self._log_audit(tool_call, ctx, None, duration, "SANDBOX_BLOCKED")
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Sandbox violation: {sandbox_reason}",
                )

        # ---- Step 4: Tool execution ----
        tool = self._tools.get(tool_call.tool_name)
        if tool is None:
            duration = time.monotonic() - start_time
            await self._log_audit(tool_call, ctx, None, duration, "TOOL_NOT_FOUND")
            return ToolResult(
                success=False,
                output=None,
                error=f"Tool not found: {tool_call.tool_name}",
            )

        try:
            result = await tool.execute(tool_call.arguments, ctx)
        except Exception as exc:
            duration = time.monotonic() - start_time
            await self._log_audit(tool_call, ctx, None, duration, "ERROR")
            return ToolResult(
                success=False,
                output=None,
                error=f"Tool execution error: {exc}",
            )

        # ---- Step 5: PostToolUse hooks + audit ----
        duration = time.monotonic() - start_time
        await self.hooks.fire(
            HookEvent.POST_TOOL_USE,
            {
                "tool_call": tool_call,
                "context": ctx,
                "result": result,
            },
        )
        await self._log_audit(tool_call, ctx, result, duration, "ALLOWED")

        return result

    # ---- internal helpers -------------------------------------------------

    def _is_write_tool(self, tool_name: str) -> bool:
        """Check if a tool performs write operations."""
        return tool_name in ("write_file", "edit_file", "shell")

    def set_permission_mode(self, mode: PermissionMode) -> None:
        """Update the kernel's permission mode."""
        self.permission_mode = mode

    def _sandbox_check(self, tool_call: ToolCall, ctx: Context) -> tuple[bool, str]:
        """Run sandbox validation. Returns (ok, reason)."""
        from octopus.core.sandbox import OperationType

        if tool_call.tool_name in ("write_file", "edit_file"):
            path = tool_call.arguments.get("path", "")
            op = (
                OperationType.WRITE
                if tool_call.tool_name == "write_file"
                else OperationType.WRITE
            )
            sr = self.sandbox.validate_path(Path(path), op)
            return sr.valid, sr.reason or ""
        if tool_call.tool_name == "shell":
            cmd = tool_call.arguments.get("command", "")
            sr = self.sandbox.validate_command(cmd)
            return sr.valid, sr.reason or ""
        return True, ""

    async def _log_audit(
        self,
        tool_call: ToolCall,
        ctx: Context,
        result: ToolResult | None,
        duration: float,
        decision: str,
    ) -> None:
        """Log an audit event."""
        from octopus.core.audit import AuditEvent

        event = AuditEvent(
            timestamp=datetime.now(UTC),
            tool=tool_call.tool_name,
            args=tool_call.arguments,
            result={"output": result.output, "success": result.success}
            if result
            else None,
            duration=duration,
            permission_decision=decision,
            session_id=ctx.session_id,
            user_id=ctx.user_id,
        )
        await self.audit.log(event)


# ---------------------------------------------------------------------------
# Global kernel singleton
# ---------------------------------------------------------------------------

_kernel_instance: Kernel | None = None


async def get_kernel(**kwargs: Any) -> Kernel:
    """Get or create the global kernel instance."""
    global _kernel_instance
    if _kernel_instance is None:
        _kernel_instance = Kernel(**kwargs)
        await _kernel_instance.initialize()
    return _kernel_instance


async def shutdown_kernel() -> None:
    """Shutdown the global kernel instance."""
    global _kernel_instance
    if _kernel_instance is not None:
        await _kernel_instance.shutdown()
        _kernel_instance = None
