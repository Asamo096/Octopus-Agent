"""Octopus Agent Kernel — Central orchestrator for harness governance.

Every agent action passes through the Kernel. The pipeline is:
1. PreToolUse hooks (permission check, rollback checkpoint)
2. Permission engine check — determines IF the operation is allowed
3. Sandbox routing — determines WHERE the operation executes
   - local: direct subprocess (default, no isolation)
   - cube: CubeSandbox KVM MicroVM (hardware isolation)
4. Tool execution (routed through sandbox backend)
5. PostToolUse hooks (audit log, result validation)
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)


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
    audit logging, sandbox routing, and other harness operations.
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
    - Sandbox          — filesystem sandbox isolation (path validation)
    - SandboxBackend   — execution backend (local subprocess or CubeSandbox MicroVM)
    - HookManager      — PreToolUse / PostToolUse lifecycle hooks
    - RollbackEngine   — task rollback via snapshots/checkpoints
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
        self.rollback: Any = None

        # Sandbox execution backend (local or cube)
        self._sandbox_backend: Any = None

        # Tool registry (populated externally)
        self._tools: dict[str, Tool] = {}

        # Permission prompt callback — set by CLI/TUI to prompt user
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
        from octopus.core.rollback import RollbackEngine
        from octopus.core.sandbox import Sandbox
        from octopus.core.state import StateManager

        # Ensure parent directory exists
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self.permissions = PermissionEngine(self.settings.get("permissions", {}))
        self.sandbox = Sandbox(self.settings.get("sandbox", {}))
        self.hooks = HookManager()
        self.audit = AuditLogger(db_path=self._db_path)
        self.state = StateManager(db_path=self._db_path)
        self.rollback = RollbackEngine(db_path=self._db_path)

        register_default_hooks(self.hooks)

        # Initialize sandbox execution backend
        await self._init_sandbox_backend()

        self._initialized = True

    async def _init_sandbox_backend(self) -> None:
        """Initialize the sandbox execution backend.

        Proactively probes CubeAPI at startup. If reachable, auto-enables
        CubeSandbox regardless of config. Falls back to local only if
        CubeAPI is unreachable, cubesandbox is not installed, or the user
        explicitly set backend=local.
        """
        sandbox_cfg = self.settings.get("sandbox", {})
        backend_name = sandbox_cfg.get("backend", "local")

        # Respect explicit local-only choice
        if backend_name == "local":
            from octopus.sandbox.local import LocalBackend
            self._sandbox_backend = LocalBackend()
            logger.info("Local sandbox backend (explicitly configured)")
            return

        # Try CubeSandbox: probe API, discover/build template, create sandbox
        api_url = sandbox_cfg.get("cube_api_url", "http://127.0.0.1:3000")
        api_key = sandbox_cfg.get("cube_api_key", "")
        template_id = sandbox_cfg.get("cube_template_id", "")
        auto_pause = sandbox_cfg.get("cube_auto_pause_timeout", 300)
        allow_internet = sandbox_cfg.get("cube_allow_internet", True)

        if not await self._probe_cube_api(api_url, api_key):
            logger.info(
                "CubeAPI not reachable at %s — using local backend. "
                "To enable CubeSandbox, deploy it first: "
                "cd ~/CubeSandbox/deploy/one-click && sudo bash install.sh",
                api_url,
            )
            from octopus.sandbox.local import LocalBackend
            self._sandbox_backend = LocalBackend()
            return

        try:
            from octopus.sandbox.cube import CubeBackend

            # Resolve template: config → discover → auto-build
            if not template_id:
                template_id = await self._discover_template(api_url, api_key)
            if not template_id:
                template_id = await self._build_default_template(api_url, api_key)
            if not template_id:
                logger.warning("Could not resolve CubeSandbox template, using local")
                from octopus.sandbox.local import LocalBackend
                self._sandbox_backend = LocalBackend()
                return

            backend = CubeBackend(
                api_url=api_url,
                template_id=template_id,
                api_key=api_key,
                auto_pause_timeout=auto_pause,
                allow_internet=allow_internet,
            )
            self._sandbox_backend = backend
            self.settings.setdefault("sandbox", {})["backend"] = "cube"
            logger.info("CubeSandbox: %s (template: %.20s)", api_url, template_id)

            # Eagerly create sandbox
            try:
                ws = str(self.workspace) if self.workspace else None
                sid = await backend.create(workspace=ws)
                logger.info("CubeSandbox created: %s", sid)
            except Exception as exc:
                logger.warning("CubeSandbox create failed (%s), will retry on use", exc)

        except ImportError:
            logger.warning("cubesandbox not installed, using local backend")
            from octopus.sandbox.local import LocalBackend
            self._sandbox_backend = LocalBackend()
        except Exception as exc:
            logger.error("CubeSandbox init failed: %s, using local", exc)
            from octopus.sandbox.local import LocalBackend
            self._sandbox_backend = LocalBackend()

    async def _probe_cube_api(
        self, api_url: str, api_key: str | None
    ) -> bool:
        """Check if CubeAPI is reachable. Returns True if healthy."""
        import asyncio
        import json
        import urllib.request

        try:
            url = f"{api_url.rstrip('/')}/health"

            def _check() -> bool:
                req = urllib.request.Request(url)
                req.add_header("Content-Type", "application/json")
                if api_key:
                    req.add_header("X-API-Key", api_key)
                with urllib.request.urlopen(req, timeout=3) as resp:  # type: ignore[attr-defined]
                    data = json.loads(resp.read().decode())
                return data.get("status") == "ok"

            ok = await asyncio.to_thread(_check)
            if ok:
                logger.info("CubeAPI health check OK: %s", api_url)
            return ok
        except Exception:
            return False

    # ---- sandbox runtime toggle -------------------------------------------

    async def enable_sandbox(self) -> str:
        """Enable CubeSandbox at runtime. Creates the MicroVM immediately.

        Template resolution order (fully automatic):
        1. Use configured cube_template_id from config/env
        2. Auto-discover existing templates from CubeAPI
        3. Auto-build a default template from python:3.11-slim

        Returns a status message describing the result.
        """
        sandbox_cfg = self.settings.get("sandbox", {})
        template_id = sandbox_cfg.get("cube_template_id", "") or os.environ.get(
            "CUBE_TEMPLATE_ID", ""
        )
        api_url = sandbox_cfg.get("cube_api_url", "http://127.0.0.1:3000")
        api_key = sandbox_cfg.get("cube_api_key", "")

        if not template_id:
            template_id = await self._discover_template(api_url, api_key)

        if not template_id:
            template_id = await self._build_default_template(api_url, api_key)

        if not template_id:
            return (
                "CubeSandbox is not running.\n\n"
                "CubeSandbox is a separate infrastructure service that must be "
                "deployed before use. Quick start:\n\n"
                "  cd ~/CubeSandbox/deploy/one-click\n"
                "  sudo bash install.sh\n\n"
                "This deploys CubeAPI, CubeProxy, and all dependencies. "
                "After deployment, CubeAPI will be available at {}.\n\n"
                "Verify with: curl {}/health\n"
                "Then run /sandbox enable again.".format(
                    api_url, api_url.rstrip("/")
                )
            )

        try:
            from octopus.sandbox.cube import CubeBackend

            # Destroy existing backend if any
            if self._sandbox_backend is not None:
                try:
                    await self._sandbox_backend.destroy()
                except Exception:
                    pass

            api_url = sandbox_cfg.get(
                "cube_api_url", "http://127.0.0.1:3000"
            )
            api_key = sandbox_cfg.get("cube_api_key", "")
            allow_internet = sandbox_cfg.get("cube_allow_internet", True)

            backend = CubeBackend(
                api_url=api_url,
                template_id=template_id,
                api_key=api_key,
                allow_internet=allow_internet,
            )
            self._sandbox_backend = backend
            self.settings.setdefault("sandbox", {})["backend"] = "cube"

            ws = str(self.workspace) if self.workspace else None
            sid = await backend.create(workspace=ws)
            logger.info("Sandbox enabled at runtime: %s", sid)
            return f"Sandbox enabled (cube, template: {template_id[:20]}...)"
        except ImportError:
            return (
                "cubesandbox package not installed. "
                "Install with: pip install -e ~/CubeSandbox/sdk/python/"
            )
        except Exception as exc:
            return f"Failed to enable sandbox: {exc}"

    async def disable_sandbox(self) -> str:
        """Disable sandbox at runtime. Destroys the CubeSandbox and falls back to local."""
        if self._sandbox_backend is not None:
            try:
                await self._sandbox_backend.destroy()
            except Exception:
                pass

        from octopus.sandbox.local import LocalBackend

        self._sandbox_backend = LocalBackend()
        self.settings.setdefault("sandbox", {})["backend"] = "local"
        logger.info("Sandbox disabled, using local backend")
        return "Sandbox disabled. Using local execution."

    def get_sandbox_status(self) -> dict[str, str]:
        """Return current sandbox state for display."""
        backend = self._sandbox_backend
        if backend is None:
            return {"backend": "none", "state": "not initialized"}

        name = getattr(backend, "name", "unknown")
        created = getattr(backend, "_created", False)
        session_id = getattr(backend, "_session_id", None)

        return {
            "backend": name,
            "state": "active" if created else "pending",
            "session_id": session_id or "",
        }

    async def _discover_template(
        self, api_url: str, api_key: str | None
    ) -> str | None:
        """Auto-discover a CubeSandbox template from the CubeAPI."""
        import asyncio

        try:
            from cubesandbox import Config, Template

            cfg = Config(api_url=api_url, api_key=api_key)

            def _list() -> str | None:
                templates = Template.list(config=cfg)
                if templates and len(templates) > 0:
                    info = templates[0]
                    tid = (
                        getattr(info, "template_id", None)
                        or getattr(info, "id", None)
                    )
                    return str(tid) if tid else None
                return None

            tid = await asyncio.to_thread(_list)
            if tid:
                logger.info("Auto-discovered template: %s", tid)
            return tid
        except Exception as exc:
            logger.debug("Template discovery failed: %s", exc)
            return None

    async def _build_default_template(
        self, api_url: str, api_key: str | None
    ) -> str | None:
        """Auto-build a default CubeSandbox template from python:3.11-slim."""
        import asyncio

        try:
            from cubesandbox import Config, Template

            cfg = Config(api_url=api_url, api_key=api_key)

            def _build() -> str | None:
                logger.info(
                    "Auto-building CubeSandbox template from python:3.11-slim ..."
                )
                job = Template.build(
                    image="python:3.11-slim",
                    name="octopus-default",
                    config=cfg,
                )
                tid = (
                    getattr(job, "template_id", None)
                    or getattr(job, "id", None)
                )
                if tid:
                    logger.info("Auto-built template: %s", str(tid))
                return str(tid) if tid else None

            tid = await asyncio.to_thread(_build)
            return tid
        except Exception as exc:
            logger.warning("Auto-build template failed: %s", exc)
            return None

    async def ensure_sandbox_created(self, ctx: Context) -> str:
        """Ensure the sandbox is created and return its session ID."""
        if self._sandbox_backend is None:
            await self._init_sandbox_backend()
        return await self._sandbox_backend.create(
            workspace=str(ctx.workspace) if ctx.workspace else None
        )

    @property
    def sandbox_backend(self) -> Any:
        """Get the active sandbox execution backend."""
        return self._sandbox_backend

    async def shutdown(self) -> None:
        """Shutdown the kernel and release resources."""
        if self._sandbox_backend is not None:
            try:
                await self._sandbox_backend.destroy()
            except Exception:
                pass
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
        1. PreToolUse hooks (rollback snapshot, pre-execution checks)
        2. Permission check — determines IF the operation is allowed
        3. Sandbox routing — determines WHERE the operation executes
        4. Tool execution (routed through sandbox backend if applicable)
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

        # Permission mode enforcement
        if self.permission_mode == PermissionMode.FULL_AUTO:
            pass  # Auto-approve everything
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
        elif self.permission_mode in (
            PermissionMode.PLAN,
            PermissionMode.ACCEPT_EDITS,
        ):
            if tool_call.tool_name == "shell":
                duration = time.monotonic() - start_time
                await self._log_audit(
                    tool_call, ctx, None, duration, "EXECUTION_BLOCKED"
                )
                return ToolResult(
                    success=False,
                    output=None,
                    error="Shell execution blocked in this mode. Switch to manual or auto mode.",
                )

        # ---- Step 3: Sandbox routing ----
        # Path-based validation (always runs for write/read tools)
        if tool_call.tool_name in ("write_file", "edit_file", "read_file"):
            sandbox_ok, sandbox_reason = self._validate_path(tool_call, ctx)
            if not sandbox_ok:
                duration = time.monotonic() - start_time
                await self._log_audit(tool_call, ctx, None, duration, "SANDBOX_BLOCKED")
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Sandbox violation: {sandbox_reason}",
                )

        # Shell commands: validate through sandbox before routing
        if tool_call.tool_name == "shell":
            sandbox_ok, sandbox_reason = self._validate_shell(tool_call, ctx)
            if not sandbox_ok:
                duration = time.monotonic() - start_time
                await self._log_audit(tool_call, ctx, None, duration, "SANDBOX_BLOCKED")
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Sandbox violation: {sandbox_reason}",
                )

            # Route shell execution through sandbox backend
            return await self._execute_in_sandbox(tool_call, ctx, start_time)

        # File operations: route through sandbox if cube backend
        if tool_call.tool_name in ("write_file", "edit_file"):
            sandbox_cfg = self.settings.get("sandbox", {})
            if sandbox_cfg.get("backend") == "cube":
                return await self._execute_in_sandbox(tool_call, ctx, start_time)

        # ---- Step 4: Direct tool execution (local backend) ----
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

    # ---- sandbox execution ------------------------------------------------

    async def _execute_in_sandbox(
        self, tool_call: ToolCall, ctx: Context, start_time: float
    ) -> ToolResult:
        """Execute a tool call through the sandbox execution backend.

        Routes shell commands and file operations through the configured
        backend (local subprocess or CubeSandbox MicroVM).
        """
        # Ensure sandbox is created
        try:
            await self.ensure_sandbox_created(ctx)
        except Exception as exc:
            duration = time.monotonic() - start_time
            await self._log_audit(tool_call, ctx, None, duration, "SANDBOX_ERROR")
            return ToolResult(
                success=False,
                output=None,
                error=f"Sandbox creation failed: {exc}",
            )

        if tool_call.tool_name == "shell":
            return await self._sandbox_execute_shell(tool_call, ctx, start_time)
        elif tool_call.tool_name in ("write_file", "edit_file"):
            return await self._sandbox_write_file(tool_call, ctx, start_time)
        else:
            # Fall back to direct tool execution
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
                duration = time.monotonic() - start_time
                await self._log_audit(tool_call, ctx, result, duration, "ALLOWED")
                return result
            except Exception as exc:
                duration = time.monotonic() - start_time
                await self._log_audit(tool_call, ctx, None, duration, "ERROR")
                return ToolResult(
                    success=False, output=None, error=f"Execution error: {exc}"
                )

    async def _sandbox_execute_shell(
        self, tool_call: ToolCall, ctx: Context, start_time: float
    ) -> ToolResult:
        """Execute a shell command through the sandbox backend."""
        command = tool_call.arguments.get("command", "")
        timeout_val = tool_call.arguments.get("timeout", 60)
        cwd = tool_call.arguments.get("workdir", None)

        try:
            sandbox_result = await self._sandbox_backend.execute_command(
                command,
                cwd=cwd,
                timeout=float(timeout_val),
            )

            output = sandbox_result.output or "(no output)"
            if sandbox_result.error and sandbox_result.exit_code != 0:
                output += f"\n[stderr]\n{sandbox_result.error}"

            result = ToolResult(
                success=sandbox_result.success,
                output=output,
                error=(
                    f"Exit code: {sandbox_result.exit_code}"
                    if not sandbox_result.success
                    else None
                ),
                metadata={
                    "exit_code": sandbox_result.exit_code,
                    "command": command,
                    "sandbox_backend": self._sandbox_backend.name,
                    "duration": sandbox_result.duration,
                },
            )
        except Exception as exc:
            result = ToolResult(
                success=False, output=None, error=f"Sandbox execution error: {exc}"
            )

        duration = time.monotonic() - start_time
        await self._log_audit(
            tool_call, ctx, result, duration, "ALLOWED"
        )
        return result

    async def _sandbox_write_file(
        self, tool_call: ToolCall, ctx: Context, start_time: float
    ) -> ToolResult:
        """Write a file through the sandbox backend."""
        path = tool_call.arguments.get("path", "")
        content = tool_call.arguments.get("content", "")

        try:
            # Create snapshot before write for rollback
            if self.rollback is not None:
                await self.rollback.checkpoint(tool_call, ctx)

            await self._sandbox_backend.write_file(path, content)

            result = ToolResult(
                success=True,
                output=f"Written: {path}",
                metadata={
                    "path": path,
                    "sandbox_backend": self._sandbox_backend.name,
                },
            )
        except Exception as exc:
            result = ToolResult(
                success=False, output=None, error=f"Sandbox write error: {exc}"
            )

        duration = time.monotonic() - start_time
        await self._log_audit(tool_call, ctx, result, duration, "ALLOWED")
        return result

    # ---- validation helpers -----------------------------------------------

    def _validate_path(
        self, tool_call: ToolCall, ctx: Context
    ) -> tuple[bool, str]:
        """Validate a file path against the sandbox rules."""
        from octopus.core.sandbox import OperationType

        path = tool_call.arguments.get("path", "")
        if not path:
            return False, "No path specified"

        op = OperationType.WRITE if tool_call.tool_name in (
            "write_file", "edit_file"
        ) else OperationType.READ

        sr = self.sandbox.validate_path(Path(path), op)
        return sr.valid, sr.reason or ""

    def _validate_shell(
        self, tool_call: ToolCall, ctx: Context
    ) -> tuple[bool, str]:
        """Validate a shell command against the sandbox rules."""
        cmd = tool_call.arguments.get("command", "")
        if not cmd:
            return False, "No command specified"
        sr = self.sandbox.validate_command(cmd)
        return sr.valid, sr.reason or ""

    def _is_write_tool(self, tool_name: str) -> bool:
        """Check if a tool performs write operations."""
        return tool_name in ("write_file", "edit_file", "shell")

    # ---- permission mode management ---------------------------------------

    def set_permission_mode(self, mode: PermissionMode) -> None:
        """Update the kernel's permission mode."""
        self.permission_mode = mode
        if self.permissions is not None:
            self.permissions.mode = mode

    def set_permission_prompt(self, prompt_callback: Any) -> None:
        """Set the permission prompt callback for user approval."""
        self._permission_prompt = prompt_callback

    # ---- audit logging ----------------------------------------------------

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
            result=(
                {"output": str(result.output)[:500], "success": result.success}
                if result
                else None
            ),
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
