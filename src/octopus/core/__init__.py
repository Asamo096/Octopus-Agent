"""Octopus Agent Core — Harness kernel components."""

from .audit import AuditEvent, AuditFilters, AuditLogger
from .hooks import Hook, HookEvent, HookManager, HookResult
from .kernel import (
    Context,
    Kernel,
    PermissionMode,
    ToolCall,
    ToolResult,
    get_kernel,
    shutdown_kernel,
)
from .permissions import PermissionEngine, PermissionResult
from .rollback import Checkpoint, FileSnapshot, RollbackEngine
from .sandbox import OperationType, Sandbox, SandboxResult
from .state import SessionState, StateManager

__all__ = [
    # kernel
    "Kernel",
    "Context",
    "ToolCall",
    "ToolResult",
    "PermissionMode",
    "get_kernel",
    "shutdown_kernel",
    # permissions
    "PermissionEngine",
    "PermissionResult",
    # audit
    "AuditLogger",
    "AuditEvent",
    "AuditFilters",
    # sandbox
    "Sandbox",
    "SandboxResult",
    "OperationType",
    # hooks
    "HookManager",
    "Hook",
    "HookEvent",
    "HookResult",
    # rollback
    "RollbackEngine",
    "Checkpoint",
    "FileSnapshot",
    # state
    "StateManager",
    "SessionState",
]
