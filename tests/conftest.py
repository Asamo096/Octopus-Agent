"""Shared test fixtures for Octopus Agent."""

from __future__ import annotations

from pathlib import Path
from typing import AsyncGenerator

import pytest

from octopus.core.kernel import Context, Kernel, PermissionMode


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """Provide a temporary workspace directory."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


@pytest.fixture
async def kernel(tmp_path: Path) -> AsyncGenerator[Kernel, None]:
    """Provide an initialized Kernel with a temporary database."""
    db_path = tmp_path / "test.db"
    k = Kernel(db_path=db_path, workspace=tmp_path)
    await k.initialize()
    yield k
    await k.shutdown()


@pytest.fixture
def ctx(kernel: Kernel, tmp_workspace: Path) -> Context:
    """Provide a Context bound to the test kernel."""
    return Context(
        session_id="test-session",
        kernel=kernel,
        workspace=tmp_workspace,
        permission_mode=PermissionMode.FULL_AUTO,
    )
