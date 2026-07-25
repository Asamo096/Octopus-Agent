"""CubeSandbox backend — hardware-isolated MicroVM sandbox.

Uses Tencent Cloud's CubeSandbox for KVM-level isolation with
sub-60ms cold start and <5MB memory overhead.

Requires: pip install cubesandbox
Server: https://github.com/TencentCloud/CubeSandbox
"""

from __future__ import annotations

import logging
import time
from typing import Any

from octopus.sandbox.adapter import SandboxResult

logger = logging.getLogger(__name__)


class CubeBackend:
    """CubeSandbox backend — hardware-isolated MicroVM execution.

    Each sandbox runs in its own Linux kernel inside a KVM MicroVM.
    Provides stronger isolation than Docker (shared kernel namespaces).

    Configuration via environment variables:
    - CUBE_API_URL: CubeAPI management plane (default: http://127.0.0.1:3000)
    - CUBE_TEMPLATE_ID: Template ID for sandbox creation
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
        self._api_url = api_url
        self._template_id = template_id
        self._api_key = api_key
        self._auto_pause_timeout = auto_pause_timeout
        self._allow_internet = allow_internet
        self._sandbox: Any = None
        self._session_id: str | None = None

    def _get_config(self) -> Any:
        """Build CubeSandbox Config from settings."""
        try:
            from cubesandbox import Config  # type: ignore[import-not-found]
        except ImportError as err:
            raise ImportError(
                "cubesandbox package not installed. "
                "Install with: pip install cubesandbox"
            ) from err

        import os

        api_url = self._api_url or os.environ.get(
            "CUBE_API_URL", "http://127.0.0.1:3000"
        )
        api_key = self._api_key or os.environ.get("CUBE_API_KEY")

        return Config(api_url=api_url, api_key=api_key)

    async def create(self, workspace: str | None = None) -> str:
        """Create a CubeSandbox MicroVM.

        Args:
            workspace: Host path to mount as /workspace

        Returns:
            Sandbox ID
        """
        try:
            from cubesandbox import Sandbox
        except ImportError as err:
            raise ImportError(
                "cubesandbox package not installed. "
                "Install with: pip install cubesandbox"
            ) from err

        import os

        template_id = self._template_id or os.environ.get("CUBE_TEMPLATE_ID")
        if not template_id:
            raise ValueError(
                "CUBE_TEMPLATE_ID must be set (env var or config). "
                "Create a template via the CubeSandbox console."
            )

        config = self._get_config()

        # Build volume mounts if workspace specified
        volume_mounts = {}
        if workspace:
            volume_mounts = {"/workspace": workspace}

        self._sandbox = Sandbox.create(
            template=template_id,
            timeout=self._auto_pause_timeout,
            config=config,
            allow_internet_access=self._allow_internet,
            volume_mounts=volume_mounts if volume_mounts else None,
        )

        self._session_id = self._sandbox.sandbox_id
        logger.info("CubeSandbox created: %s", self._session_id)
        return self._session_id

    async def execute_command(
        self,
        command: str,
        *,
        cwd: str | None = None,
        timeout: float = 30.0,
    ) -> SandboxResult:
        """Execute a shell command in the CubeSandbox MicroVM."""
        if self._sandbox is None:
            return SandboxResult(success=False, error="Sandbox not created")

        start = time.monotonic()
        try:
            result = self._sandbox.commands.run(
                command,
                cwd=cwd or "/workspace",
                timeout=int(timeout),
            )
            duration = time.monotonic() - start

            return SandboxResult(
                success=result.exit_code == 0,
                output=result.stdout if hasattr(result, "stdout") else str(result),
                error=result.stderr
                if hasattr(result, "stderr") and result.exit_code != 0
                else None,
                exit_code=result.exit_code if hasattr(result, "exit_code") else 0,
                duration=duration,
            )
        except Exception as e:
            return SandboxResult(
                success=False,
                error=str(e),
                exit_code=-1,
                duration=time.monotonic() - start,
            )

    async def read_file(self, path: str) -> str:
        """Read a file from the CubeSandbox."""
        if self._sandbox is None:
            raise RuntimeError("Sandbox not created")
        content: str = self._sandbox.files.read(path)
        return content

    async def write_file(self, path: str, content: str) -> None:
        """Write a file to the CubeSandbox."""
        if self._sandbox is None:
            raise RuntimeError("Sandbox not created")
        self._sandbox.files.write(path, content)

    async def create_snapshot(self, name: str) -> str:
        """Create a snapshot of the CubeSandbox state."""
        if self._sandbox is None:
            raise RuntimeError("Sandbox not created")
        snapshot = self._sandbox.create_snapshot(name)
        return (
            snapshot.snapshot_id if hasattr(snapshot, "snapshot_id") else str(snapshot)
        )

    async def restore_snapshot(self, snapshot_id: str) -> None:
        """Restore the CubeSandbox to a snapshot."""
        if self._sandbox is None:
            raise RuntimeError("Sandbox not created")
        self._sandbox.rollback(snapshot_id)

    async def destroy(self) -> None:
        """Destroy the CubeSandbox MicroVM."""
        if self._sandbox is not None:
            try:
                self._sandbox.kill()
                logger.info("CubeSandbox destroyed: %s", self._session_id)
            except Exception as e:
                logger.warning("Failed to destroy sandbox: %s", e)
            finally:
                self._sandbox = None
                self._session_id = None
