"""Tests for octopus.sandbox — local and CubeSandbox backends."""

from __future__ import annotations

from pathlib import Path

import pytest

from octopus.sandbox.local import LocalBackend


class TestLocalBackend:
    async def test_create(self) -> None:
        backend = LocalBackend()
        session_id = await backend.create("/tmp")
        assert session_id == "local"

    async def test_execute_command(self) -> None:
        backend = LocalBackend()
        await backend.create()
        result = await backend.execute_command("echo hello")
        assert result.success
        assert "hello" in result.output

    async def test_execute_command_failure(self) -> None:
        backend = LocalBackend()
        await backend.create()
        result = await backend.execute_command("false")
        assert not result.success
        assert result.exit_code != 0

    async def test_execute_command_timeout(self) -> None:
        backend = LocalBackend()
        await backend.create()
        result = await backend.execute_command("sleep 10", timeout=0.1)
        assert not result.success
        assert "timed out" in result.error

    async def test_read_write_file(self, tmp_path: Path) -> None:
        backend = LocalBackend()
        await backend.create()

        test_file = tmp_path / "test.txt"
        await backend.write_file(str(test_file), "hello world")
        content = await backend.read_file(str(test_file))
        assert content == "hello world"

    async def test_snapshot_not_supported(self) -> None:
        backend = LocalBackend()
        await backend.create()
        with pytest.raises(NotImplementedError):
            await backend.create_snapshot("test")

    async def test_destroy_noop(self) -> None:
        backend = LocalBackend()
        await backend.create()
        await backend.destroy()  # Should not raise


class TestCubeBackend:
    def test_import_without_package(self) -> None:
        """CubeBackend should be importable even without cubesandbox package."""
        from octopus.sandbox.cube import CubeBackend

        backend = CubeBackend()
        assert backend.name == "cube"

    def test_config_defaults(self) -> None:
        from octopus.sandbox.cube import CubeBackend

        backend = CubeBackend(
            api_url="http://localhost:3000",
            template_id="tpl-test",
            auto_pause_timeout=600,
        )
        assert backend._api_url == "http://localhost:3000"
        assert backend._template_id == "tpl-test"
        assert backend._auto_pause_timeout == 600
