"""CubeSandbox backend — hardware-isolated MicroVM sandbox.

Uses Tencent Cloud's CubeSandbox for KVM-level isolation with
sub-60ms cold start and <5MB memory overhead.

The CubeSandbox SDK is synchronous, so this adapter bridges to
the async kernel via asyncio.to_thread().

Requires: pip install cubesandbox (installed from ~/CubeSandbox/sdk/python/)
Server: https://github.com/TencentCloud/CubeSandbox
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SandboxResult:
    """Result of a sandbox operation."""

    success: bool
    output: str | None = None
    error: str | None = None
    exit_code: int = 0
    duration: float = 0.0


class CubeBackend:
    """CubeSandbox backend — hardware-isolated MicroVM execution.

    Each sandbox runs in its own Linux kernel inside a KVM MicroVM.
    Provides stronger isolation than Docker (shared kernel namespaces).

    The backend wraps the synchronous CubeSandbox SDK and exposes
    async methods for the Octopus kernel via asyncio.to_thread().

    Configuration via environment variables or constructor args:
    - CUBE_API_URL: CubeAPI management plane (default: http://127.0.0.1:3000)
    - CUBE_TEMPLATE_ID: Template ID for sandbox creation (required)
    - CUBE_API_KEY: Optional API key
    """

    name = "cube"

    def __init__(
        self,
        *,
        api_url: str | None = None,
        template_id: str | None = None,
        api_key: str | None = None,
        auto_pause_timeout: int = 300,
        allow_internet: bool = True,
    ) -> None:
        self._api_url = api_url or os.environ.get(
            "CUBE_API_URL", "http://127.0.0.1:3000"
        )
        self._template_id = template_id or os.environ.get("CUBE_TEMPLATE_ID", "")
        self._api_key = api_key or os.environ.get("CUBE_API_KEY")
        self._auto_pause_timeout = auto_pause_timeout
        self._allow_internet = allow_internet
        self._sandbox: object | None = None
        self._session_id: str | None = None
        self._created = False

    # ---- lifecycle ----------------------------------------------------------

    async def create(self, workspace: str | None = None) -> str:
        """Create a CubeSandbox MicroVM.

        Uses asyncio.to_thread() because the CubeSandbox SDK is synchronous.
        The Sandbox.create() call blocks until the VM is ready.

        Returns the sandbox ID.
        """
        if self._created and self._sandbox is not None:
            return self._session_id or ""

        if not self._template_id:
            raise ValueError(
                "CUBE_TEMPLATE_ID must be set. Create a template via the "
                "CubeSandbox console and set it in config or env."
            )

        def _create() -> object:
            from cubesandbox import Config, Sandbox

            cfg = Config(
                api_url=self._api_url,
                api_key=self._api_key,
                template_id=self._template_id,
            )

            volume_mounts = None
            if workspace:
                volume_mounts = {"/workspace": workspace}

            sb = Sandbox.create(
                template=self._template_id,
                timeout=self._auto_pause_timeout,
                allow_internet_access=self._allow_internet,
                volume_mounts=volume_mounts,
                config=cfg,
            )
            return sb

        try:
            self._sandbox = await asyncio.to_thread(_create)
            self._session_id = getattr(self._sandbox, "sandbox_id", None)
            self._created = True
            logger.info("CubeSandbox created: %s", self._session_id)
            return self._session_id or ""
        except ImportError:
            raise ImportError(
                "cubesandbox package not installed. "
                "Install with: pip install -e ~/CubeSandbox/sdk/python/"
            )
        except Exception as exc:
            logger.error("CubeSandbox creation failed: %s", exc)
            raise

    async def execute_command(
        self,
        command: str,
        *,
        cwd: str | None = None,
        timeout: float = 30.0,
    ) -> SandboxResult:
        """Execute a shell command inside the CubeSandbox MicroVM.

        Uses sb.commands.run() which connects via envd's Connect protocol.
        """
        if self._sandbox is None:
            return SandboxResult(
                success=False, error="Sandbox not created. Call create() first."
            )

        start = time.monotonic()

        def _run() -> object:
            sb = self._sandbox
            result = sb.commands.run(  # type: ignore[union-attr]
                command,
                timeout=timeout,
                cwd=cwd or "/workspace",
            )
            return result

        try:
            cmd_result = await asyncio.to_thread(_run)
            duration = time.monotonic() - start
            return SandboxResult(
                success=cmd_result.exit_code == 0,  # type: ignore[union-attr]
                output=cmd_result.stdout,  # type: ignore[union-attr]
                error=(
                    cmd_result.stderr  # type: ignore[union-attr]
                    if cmd_result.exit_code != 0  # type: ignore[union-attr]
                    else None
                ),
                exit_code=cmd_result.exit_code,  # type: ignore[union-attr]
                duration=duration,
            )
        except Exception as exc:
            return SandboxResult(
                success=False,
                error=str(exc),
                exit_code=-1,
                duration=time.monotonic() - start,
            )

    async def read_file(self, path: str) -> str:
        """Read a file from inside the CubeSandbox."""
        if self._sandbox is None:
            raise RuntimeError("Sandbox not created")

        def _read() -> str:
            sb = self._sandbox
            return sb.files.read(path)  # type: ignore[union-attr]

        return await asyncio.to_thread(_read)

    async def write_file(self, path: str, content: str) -> None:
        """Write a file inside the CubeSandbox."""
        if self._sandbox is None:
            raise RuntimeError("Sandbox not created")

        def _write() -> None:
            sb = self._sandbox
            sb.files.write(path, content)  # type: ignore[union-attr]

        await asyncio.to_thread(_write)

    async def create_snapshot(self, name: str) -> str:
        """Create a snapshot of the CubeSandbox state.

        Snapshots capture the full filesystem and memory state.
        They persist independently of the sandbox lifecycle.
        """
        if self._sandbox is None:
            raise RuntimeError("Sandbox not created")

        def _snap() -> object:
            sb = self._sandbox
            return sb.create_snapshot(name)  # type: ignore[union-attr]

        snapshot = await asyncio.to_thread(_snap)
        return getattr(snapshot, "snapshot_id", str(snapshot))

    async def restore_snapshot(self, snapshot_id: str) -> None:
        """Restore the CubeSandbox to a previous snapshot.

        Reverts filesystem and memory state. The VM restarts with a
        new kernel after rollback.
        """
        if self._sandbox is None:
            raise RuntimeError("Sandbox not created")

        def _rollback() -> None:
            sb = self._sandbox
            sb.rollback(snapshot_id)  # type: ignore[union-attr]

        await asyncio.to_thread(_rollback)

    async def destroy(self) -> None:
        """Destroy the CubeSandbox MicroVM."""
        if self._sandbox is not None:

            def _kill() -> None:
                sb = self._sandbox
                sb.kill()  # type: ignore[union-attr]

            try:
                await asyncio.to_thread(_kill)
                logger.info("CubeSandbox destroyed: %s", self._session_id)
            except Exception as exc:
                logger.warning("Failed to destroy sandbox: %s", exc)
            finally:
                self._sandbox = None
                self._session_id = None
                self._created = False
