"""
Octopus Agent Hooks - PreToolUse/PostToolUse lifecycle hooks.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any


class HookEvent(Enum):
    """Hook events."""

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


@dataclass
class HookResult:
    """Result of a hook execution."""

    continue_execution: bool
    modified_data: dict[str, Any] | None = None
    error: str | None = None


class Hook:
    """Represents a hook function."""

    def __init__(self, name: str, callback: Callable, priority: int = 0):
        """Initialize a hook."""
        self.name = name
        self.callback = callback
        self.priority = priority

    async def execute(self, data: dict[str, Any]) -> HookResult:
        """Execute the hook."""
        try:
            result = await self.callback(data)
            if isinstance(result, HookResult):
                return result
            elif isinstance(result, bool):
                return HookResult(continue_execution=result)
            else:
                return HookResult(continue_execution=True)
        except Exception as e:
            return HookResult(
                continue_execution=False, error=f"Hook {self.name} failed: {str(e)}"
            )


class HookManager:
    """PreToolUse/PostToolUse lifecycle hooks."""

    def __init__(self) -> None:
        """Initialize the hook manager."""
        self.hooks: dict[HookEvent, list[Hook]] = {}
        self._initialized = False

    def register(self, event: HookEvent, hook: Hook) -> None:
        """Register a hook for an event."""
        if event not in self.hooks:
            self.hooks[event] = []

        # Insert hook maintaining priority order (higher priority first)
        self.hooks[event].append(hook)
        self.hooks[event].sort(key=lambda h: h.priority, reverse=True)

    def unregister(self, event: HookEvent, hook_name: str) -> None:
        """Unregister a hook by name."""
        if event in self.hooks:
            self.hooks[event] = [h for h in self.hooks[event] if h.name != hook_name]

    async def fire(self, event: HookEvent, data: dict[str, Any]) -> HookResult:
        """Fire all hooks for an event."""
        if event not in self.hooks:
            return HookResult(continue_execution=True)

        # Execute hooks in priority order
        for hook in self.hooks[event]:
            result = await hook.execute(data)

            # If hook says to stop, return immediately
            if not result.continue_execution:
                return result

            # If hook modified data, update the data for next hook
            if result.modified_data:
                data.update(result.modified_data)

        return HookResult(continue_execution=True, modified_data=data)

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


# Built-in hooks
async def permission_check_hook(data: dict[str, Any]) -> HookResult:
    """Hook for permission checking."""
    # This is a placeholder for actual permission checking logic
    return HookResult(continue_execution=True)


async def audit_log_hook(data: dict[str, Any]) -> HookResult:
    """Hook for audit logging."""
    # This is a placeholder for actual audit logging logic
    return HookResult(continue_execution=True)


async def rollback_checkpoint_hook(data: dict[str, Any]) -> HookResult:
    """Hook for creating rollback checkpoints."""
    # This is a placeholder for actual checkpoint creation logic
    return HookResult(continue_execution=True)


def register_default_hooks(hook_manager: HookManager) -> None:
    """Register default hooks."""
    # Register permission check hook
    hook_manager.register(
        HookEvent.PERMISSION_CHECK,
        Hook("permission_check", permission_check_hook, priority=100),
    )

    # Register audit log hook
    hook_manager.register(
        HookEvent.AUDIT_LOG, Hook("audit_log", audit_log_hook, priority=50)
    )

    # Register rollback checkpoint hook
    hook_manager.register(
        HookEvent.PRE_TOOL_USE,
        Hook("rollback_checkpoint", rollback_checkpoint_hook, priority=90),
    )
