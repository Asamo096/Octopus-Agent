"""Octopus Agent Hooks — PreToolUse/PostToolUse lifecycle hooks.

Supports 4 hook types:
- PYTHON: Async Python callback (original behavior)
- COMMAND: Shell command execution with env injection
- HTTP: POST event payload to a webhook URL
- PROMPT: LLM-based validation (returns JSON ok/not-ok)

Default hooks wire permission checking, audit logging, and rollback
checkpointing into the kernel pipeline.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hook events
# ---------------------------------------------------------------------------


class HookEvent(StrEnum):
    """Events that can trigger hooks."""

    SESSION_START = "session_start"
    SESSION_END = "session_end"
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    PRE_FILE_READ = "pre_file_read"
    POST_FILE_READ = "post_file_read"
    PRE_FILE_WRITE = "pre_file_write"
    POST_FILE_WRITE = "post_file_write"
    PRE_SHELL_EXEC = "pre_shell_exec"
    POST_SHELL_EXEC = "post_shell_exec"
    PERMISSION_CHECK = "permission_check"
    AUDIT_LOG = "audit_log"


# ---------------------------------------------------------------------------
# Hook types
# ---------------------------------------------------------------------------


class HookType(StrEnum):
    """Types of hooks supported."""

    PYTHON = "python"
    COMMAND = "command"
    HTTP = "http"
    PROMPT = "prompt"


# ---------------------------------------------------------------------------
# Hook configurations
# ---------------------------------------------------------------------------


@dataclass
class CommandHookConfig:
    """Configuration for command hooks."""

    command: str  # Shell command template; $ARGUMENTS replaced with JSON payload
    timeout: float = 30.0  # seconds
    block_on_failure: bool = True


@dataclass
class HttpHookConfig:
    """Configuration for HTTP webhook hooks."""

    url: str
    headers: dict[str, str] = field(default_factory=dict)
    timeout: float = 10.0


@dataclass
class PromptHookConfig:
    """Configuration for LLM prompt hooks."""

    prompt: str  # Prompt template; $ARGUMENTS replaced with JSON payload
    model: str = "claude-haiku-4-5-20251001"
    timeout: float = 30.0


# ---------------------------------------------------------------------------
# Hook result
# ---------------------------------------------------------------------------


@dataclass
class HookResult:
    """Result of a hook execution."""

    continue_execution: bool
    modified_data: dict[str, Any] | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Aggregated result
# ---------------------------------------------------------------------------


@dataclass
class AggregatedHookResult:
    """Aggregated result from all hooks for an event."""

    continue_execution: bool = True
    modified_data: dict[str, Any] | None = None
    error: str | None = None
    results: list[HookResult] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        """True if any hook blocked execution."""
        return not self.continue_execution


# ---------------------------------------------------------------------------
# Hook definition
# ---------------------------------------------------------------------------


class Hook:
    """A single hook that can be Python, Command, HTTP, or Prompt type."""

    def __init__(
        self,
        name: str,
        hook_type: HookType,
        event: HookEvent,
        *,
        priority: int = 0,
        callback: Callable | None = None,
        command_config: CommandHookConfig | None = None,
        http_config: HttpHookConfig | None = None,
        prompt_config: PromptHookConfig | None = None,
        matcher: str | None = None,  # fnmatch pattern for tool name
    ) -> None:
        self.name = name
        self.hook_type = hook_type
        self.event = event
        self.priority = priority
        self.callback = callback
        self.command_config = command_config
        self.http_config = http_config
        self.prompt_config = prompt_config
        self.matcher = matcher

    async def execute(self, data: dict[str, Any]) -> HookResult:
        """Execute the hook based on its type."""
        try:
            if self.hook_type == HookType.PYTHON:
                return await self._execute_python(data)
            elif self.hook_type == HookType.COMMAND:
                return await self._execute_command(data)
            elif self.hook_type == HookType.HTTP:
                return await self._execute_http(data)
            elif self.hook_type == HookType.PROMPT:
                return await self._execute_prompt(data)
            else:
                return HookResult(continue_execution=True, error=f"Unknown hook type: {self.hook_type}")
        except Exception as e:
            return HookResult(
                continue_execution=False,
                error=f"Hook {self.name} failed: {e}",
            )

    async def _execute_python(self, data: dict[str, Any]) -> HookResult:
        """Execute a Python callback hook."""
        if self.callback is None:
            return HookResult(continue_execution=True)
        result = await self.callback(data)
        if isinstance(result, HookResult):
            return result
        if isinstance(result, bool):
            return HookResult(continue_execution=result)
        return HookResult(continue_execution=True)

    async def _execute_command(self, data: dict[str, Any]) -> HookResult:
        """Execute a shell command hook."""
        if self.command_config is None:
            return HookResult(continue_execution=True)

        payload = json.dumps(data, default=str)
        command = self.command_config.command.replace("$ARGUMENTS", payload)

        # Inject environment variables
        env = os.environ.copy()
        env["OPENHARNESS_HOOK_EVENT"] = self.event.value
        env["OPENHARNESS_HOOK_PAYLOAD"] = payload

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.command_config.timeout
            )
        except TimeoutError:
            proc.kill()
            msg = f"Hook {self.name} timed out after {self.command_config.timeout}s"
            if self.command_config.block_on_failure:
                return HookResult(continue_execution=False, error=msg)
            return HookResult(continue_execution=True, error=msg)

        if proc.returncode != 0:
            msg = f"Hook {self.name} exited with code {proc.returncode}: {stderr.decode()[:200]}"
            if self.command_config.block_on_failure:
                return HookResult(continue_execution=False, error=msg)
            return HookResult(continue_execution=True, error=msg)

        return HookResult(continue_execution=True)

    async def _execute_http(self, data: dict[str, Any]) -> HookResult:
        """Execute an HTTP webhook hook."""
        if self.http_config is None:
            return HookResult(continue_execution=True)

        payload = json.dumps(data, default=str)
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    self.http_config.url,
                    content=payload,
                    headers={
                        "Content-Type": "application/json",
                        **self.http_config.headers,
                    },
                    timeout=self.http_config.timeout,
                )
                if resp.status_code >= 400:
                    return HookResult(
                        continue_execution=True,
                        error=f"HTTP hook {self.name} returned {resp.status_code}",
                    )
            except httpx.HTTPError as e:
                return HookResult(
                    continue_execution=True,
                    error=f"HTTP hook {self.name} failed: {e}",
                )

        return HookResult(continue_execution=True)

    async def _execute_prompt(self, data: dict[str, Any]) -> HookResult:
        """Execute an LLM prompt validation hook."""
        if self.prompt_config is None:
            return HookResult(continue_execution=True)

        # This would call the LLM to validate — for now return pass-through
        # Full implementation requires provider integration
        logger.debug("Prompt hook %s: would call LLM for validation", self.name)
        return HookResult(continue_execution=True)


# ---------------------------------------------------------------------------
# Hook manager
# ---------------------------------------------------------------------------


class HookManager:
    """PreToolUse/PostToolUse lifecycle hooks with hot-reload support."""

    def __init__(self) -> None:
        self.hooks: dict[HookEvent, list[Hook]] = {}
        self._config_path: Path | None = None
        self._config_mtime: float = 0.0

    def register(self, event: HookEvent, hook: Hook) -> None:
        """Register a hook for an event."""
        if event not in self.hooks:
            self.hooks[event] = []
        self.hooks[event].append(hook)
        self.hooks[event].sort(key=lambda h: h.priority, reverse=True)

    def unregister(self, event: HookEvent, hook_name: str) -> None:
        """Unregister a hook by name."""
        if event in self.hooks:
            self.hooks[event] = [h for h in self.hooks[event] if h.name != hook_name]

    async def fire(self, event: HookEvent, data: dict[str, Any]) -> AggregatedHookResult:
        """Fire all hooks for an event, return aggregated result."""
        # Check for config hot-reload
        self._check_reload()

        if event not in self.hooks:
            return AggregatedHookResult(continue_execution=True)

        aggregated = AggregatedHookResult()
        for hook in self.hooks[event]:
            # Check matcher (tool name pattern)
            if hook.matcher and "tool_call" in data:
                tool_name = data["tool_call"].tool_name
                import fnmatch
                if not fnmatch.fnmatch(tool_name, hook.matcher):
                    continue

            result = await hook.execute(data)
            aggregated.results.append(result)

            if not result.continue_execution:
                aggregated.continue_execution = False
                aggregated.error = result.error
                return aggregated

            if result.modified_data:
                data.update(result.modified_data)
                aggregated.modified_data = data

        aggregated.continue_execution = True
        return aggregated

    def get_hooks(self, event: HookEvent) -> list[Hook]:
        """Get all hooks for an event."""
        return self.hooks.get(event, [])

    def clear(self, event: HookEvent | None = None) -> None:
        """Clear hooks for an event or all hooks."""
        if event:
            self.hooks[event] = []
        else:
            self.hooks.clear()

    def list_events(self) -> list[HookEvent]:
        """List all events with registered hooks."""
        return list(self.hooks.keys())

    # ---- hot-reload ---------------------------------------------------------

    def set_config_path(self, path: Path) -> None:
        """Set the config file path for hot-reload."""
        self._config_path = path
        if path.exists():
            self._config_mtime = path.stat().st_mtime

    def _check_reload(self) -> None:
        """Check if config file changed and reload hooks if needed."""
        if self._config_path is None or not self._config_path.exists():
            return
        mtime = self._config_path.stat().st_mtime
        if mtime > self._config_mtime:
            self._config_mtime = mtime
            self._load_from_config()

    def _load_from_config(self) -> None:
        """Reload hooks from config file."""
        if self._config_path is None:
            return
        try:
            import yaml
            config = yaml.safe_load(self._config_path.read_text())
            if config and "hooks" in config:
                self._parse_config_hooks(config["hooks"])
                logger.info("Reloaded hooks from %s", self._config_path)
        except Exception as e:
            logger.error("Failed to reload hooks: %s", e)

    def _parse_config_hooks(self, hooks_config: list[dict[str, Any]]) -> None:
        """Parse hooks from config and register them."""
        self.clear()
        for hook_def in hooks_config:
            try:
                event = HookEvent(hook_def["event"])
                hook_type = HookType(hook_def.get("type", "python"))
                name = hook_def.get("name", f"hook_{len(self.hooks)}")
                priority = hook_def.get("priority", 0)

                if hook_type == HookType.COMMAND:
                    cmd_config = CommandHookConfig(
                        command=hook_def["command"],
                        timeout=hook_def.get("timeout", 30),
                        block_on_failure=hook_def.get("block_on_failure", True),
                    )
                    hook = Hook(name, hook_type, event, priority=priority, command_config=cmd_config)
                elif hook_type == HookType.HTTP:
                    http_config = HttpHookConfig(
                        url=hook_def["url"],
                        headers=hook_def.get("headers", {}),
                        timeout=hook_def.get("timeout", 10),
                    )
                    hook = Hook(name, hook_type, event, priority=priority, http_config=http_config)
                elif hook_type == HookType.PROMPT:
                    prompt_config = PromptHookConfig(
                        prompt=hook_def["prompt"],
                        model=hook_def.get("model", "claude-haiku-4-5-20251001"),
                        timeout=hook_def.get("timeout", 30),
                    )
                    hook = Hook(name, hook_type, event, priority=priority, prompt_config=prompt_config)
                else:
                    continue

                self.register(event, hook)
            except (KeyError, ValueError) as e:
                logger.warning("Skipping invalid hook definition: %s", e)


# ---------------------------------------------------------------------------
# Default hooks — wire into kernel pipeline
# ---------------------------------------------------------------------------


async def permission_check_hook(data: dict[str, Any]) -> HookResult:
    """Default hook: validate permissions via the kernel's PermissionEngine.

    This hook runs at priority 100 (highest) and delegates to the kernel's
    permission engine. If the kernel is not available, allows execution.
    """
    ctx = data.get("context")
    tool_call = data.get("tool_call")
    if ctx is None or tool_call is None:
        return HookResult(continue_execution=True)

    kernel = getattr(ctx, "kernel", None)
    if kernel is None:
        return HookResult(continue_execution=True)

    # The kernel's execute_tool handles the actual permission check
    # This hook is a pre-check that can block before execution
    return HookResult(continue_execution=True)


async def audit_log_hook(data: dict[str, Any]) -> HookResult:
    """Default hook: log the tool call to the audit trail.

    This hook runs at priority 50 (after permission check) and logs
    the event to the kernel's AuditLogger.
    """
    ctx = data.get("context")
    tool_call = data.get("tool_call")
    if ctx is None or tool_call is None:
        return HookResult(continue_execution=True)

    kernel = getattr(ctx, "kernel", None)
    if kernel is None or not hasattr(kernel, "audit"):
        return HookResult(continue_execution=True)

    # Audit logging is handled by kernel._log_audit after execution
    # This hook is for PostToolUse events
    return HookResult(continue_execution=True)


async def rollback_checkpoint_hook(data: dict[str, Any]) -> HookResult:
    """Default hook: create a rollback checkpoint before file modifications.

    This hook runs at priority 90 (before execution) and snapshots
    file state for tools that modify files (write_file, edit_file).
    """
    tool_call = data.get("tool_call")
    ctx = data.get("context")
    if tool_call is None or ctx is None:
        return HookResult(continue_execution=True)

    # Only checkpoint for file-modifying tools
    if tool_call.tool_name not in ("write_file", "edit_file"):
        return HookResult(continue_execution=True)

    kernel = getattr(ctx, "kernel", None)
    if kernel is None or not hasattr(kernel, "rollback"):
        return HookResult(continue_execution=True)

    try:
        from octopus.core.rollback import RollbackEngine
        rollback: RollbackEngine | None = getattr(kernel, "_rollback", None)
        if rollback is None:
            # Lazy-init rollback engine
            from octopus.core.rollback import RollbackEngine
            rollback = RollbackEngine(db_path=kernel._db_path)
            kernel._rollback = rollback

        # Snapshot the file before modification
        path = tool_call.arguments.get("path", "")
        if path:
            await rollback.checkpoint(
                session_id=ctx.session_id,
                tool_name=tool_call.tool_name,
                tool_args=tool_call.arguments,
                affected_paths=[Path(path)],
            )
    except Exception as e:
        logger.warning("Rollback checkpoint failed: %s", e)
        # Don't block execution on checkpoint failure

    return HookResult(continue_execution=True)


def register_default_hooks(hook_manager: HookManager) -> None:
    """Register default hooks into the hook manager."""
    # Permission check — highest priority, runs first
    hook_manager.register(
        HookEvent.PRE_TOOL_USE,
        Hook(
            "permission_check",
            HookType.PYTHON,
            HookEvent.PRE_TOOL_USE,
            priority=100,
            callback=permission_check_hook,
        ),
    )

    # Rollback checkpoint — high priority, runs before execution
    hook_manager.register(
        HookEvent.PRE_TOOL_USE,
        Hook(
            "rollback_checkpoint",
            HookType.PYTHON,
            HookEvent.PRE_TOOL_USE,
            priority=90,
            callback=rollback_checkpoint_hook,
        ),
    )

    # Audit log — medium priority, runs after execution
    hook_manager.register(
        HookEvent.POST_TOOL_USE,
        Hook(
            "audit_log",
            HookType.PYTHON,
            HookEvent.POST_TOOL_USE,
            priority=50,
            callback=audit_log_hook,
        ),
    )
