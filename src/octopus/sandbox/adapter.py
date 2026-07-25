"""Sandbox adapter protocol — defines the interface for sandbox backends."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class SandboxResult:
    """Result of a sandbox operation."""

    success: bool
    output: str | None = None
    error: str | None = None
    exit_code: int = 0
    duration: float = 0.0


class SandboxAdapter(Protocol):
    """Protocol that all sandbox backends must implement."""

    name: str

    async def create(self, workspace: str | None = None) -> str:
        """Create a sandbox session. Returns session ID."""
        ...

    async def execute_command(
        self,
        command: str,
        *,
        cwd: str | None = None,
        timeout: float = 30.0,
    ) -> SandboxResult:
        """Execute a shell command in the sandbox."""
        ...

    async def read_file(self, path: str) -> str:
        """Read a file from the sandbox."""
        ...

    async def write_file(self, path: str, content: str) -> None:
        """Write a file to the sandbox."""
        ...

    async def create_snapshot(self, name: str) -> str:
        """Create a snapshot. Returns snapshot ID."""
        ...

    async def restore_snapshot(self, snapshot_id: str) -> None:
        """Restore the sandbox to a snapshot."""
        ...

    async def destroy(self) -> None:
        """Destroy the sandbox session."""
        ...
