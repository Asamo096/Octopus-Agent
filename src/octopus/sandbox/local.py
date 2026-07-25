"""Local sandbox backend — subprocess execution with no isolation.

This is the default backend when CubeSandbox is not available.
It provides no process isolation but works everywhere.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from octopus.sandbox.adapter import SandboxResult

logger = logging.getLogger(__name__)


class LocalBackend:
    """Local sandbox — runs commands in subprocesses with no isolation.

    This is the fallback when CubeSandbox is not installed.
    """

    name = "local"

    def __init__(self) -> None:
        self._workspace: str | None = None

    async def create(self, workspace: str | None = None) -> str:
        """Create a local sandbox session (no-op)."""
        self._workspace = workspace
        return "local"

    async def execute_command(
        self,
        command: str,
        *,
        cwd: str | None = None,
        timeout: float = 30.0,
    ) -> SandboxResult:
        """Execute a command in a local subprocess."""
        start = time.monotonic()
        workdir = cwd or self._workspace

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workdir,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            duration = time.monotonic() - start

            return SandboxResult(
                success=proc.returncode == 0,
                output=stdout.decode(errors="replace"),
                error=stderr.decode(errors="replace") if proc.returncode != 0 else None,
                exit_code=proc.returncode or 0,
                duration=duration,
            )
        except TimeoutError:
            proc.kill()
            return SandboxResult(
                success=False,
                error=f"Command timed out after {timeout}s",
                exit_code=-1,
                duration=time.monotonic() - start,
            )
        except Exception as e:
            return SandboxResult(
                success=False,
                error=str(e),
                exit_code=-1,
                duration=time.monotonic() - start,
            )

    async def read_file(self, path: str) -> str:
        """Read a file from the local filesystem."""
        return Path(path).read_text()

    async def write_file(self, path: str, content: str) -> None:
        """Write a file to the local filesystem."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)

    async def create_snapshot(self, name: str) -> str:
        """Snapshots not supported in local backend."""
        raise NotImplementedError("Snapshots require CubeSandbox backend")

    async def restore_snapshot(self, snapshot_id: str) -> None:
        """Snapshots not supported in local backend."""
        raise NotImplementedError("Snapshots require CubeSandbox backend")

    async def destroy(self) -> None:
        """Destroy the local sandbox session (no-op)."""
        pass
