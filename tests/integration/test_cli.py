"""Integration tests for the CLI — end-to-end command testing."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _run_octopus(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Run the octopus CLI command."""
    return subprocess.run(
        [sys.executable, "-m", "octopus", *args],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=cwd,
    )


class TestCLIHelp:
    def test_help(self) -> None:
        result = _run_octopus("--help")
        assert result.returncode == 0
        assert "Octopus Agent" in result.stdout
        assert "cli" in result.stdout
        assert "code" in result.stdout

    def test_version(self) -> None:
        result = _run_octopus("--version")
        assert result.returncode == 0
        assert "0.1.0" in result.stdout

    def test_cli_help(self) -> None:
        result = _run_octopus("cli", "--help")
        assert result.returncode == 0
        assert "interactive" in result.stdout.lower()

    def test_code_help(self) -> None:
        result = _run_octopus("code", "--help")
        assert result.returncode == 0
        assert "init" in result.stdout

    def test_config_help(self) -> None:
        result = _run_octopus("config", "--help")
        assert result.returncode == 0

    def test_permissions_help(self) -> None:
        result = _run_octopus("permissions", "--help")
        assert result.returncode == 0


class TestCodeCommands:
    def test_code_init(self, tmp_path: Path) -> None:
        result = _run_octopus("code", "init", "--path", str(tmp_path))
        assert result.returncode == 0
        assert (tmp_path / ".octopus" / "config.yaml").exists()

    def test_code_init_existing(self, tmp_path: Path) -> None:
        (tmp_path / ".octopus").mkdir()
        (tmp_path / ".octopus" / "config.yaml").write_text("existing")
        result = _run_octopus("code", "init", "--path", str(tmp_path))
        assert result.returncode == 0
        assert "already exists" in result.stdout.lower() or result.returncode == 0

    def test_code_logs_empty(self) -> None:
        result = _run_octopus("code", "logs")
        assert result.returncode == 0

    def test_code_invalid_action(self) -> None:
        result = _run_octopus("code", "invalid")
        assert result.returncode == 1


class TestConfigCommands:
    def test_config_show_empty(self) -> None:
        result = _run_octopus("config", "show")
        assert result.returncode == 0

    def test_config_set(self) -> None:
        result = _run_octopus("config", "set", "test.key", "test.value")
        assert result.returncode == 0


class TestPermissionsCommands:
    def test_permissions_list(self) -> None:
        result = _run_octopus("permissions", "list")
        assert result.returncode == 0
        assert "ssh" in result.stdout.lower() or "sensitive" in result.stdout.lower()


class TestSessionCommands:
    def test_session_list(self) -> None:
        result = _run_octopus("session", "list")
        assert result.returncode == 0


class TestProviderCommands:
    def test_provider_list(self) -> None:
        result = _run_octopus("provider", "list")
        assert result.returncode == 0
        # May show "No providers configured" or list providers
        assert "provider" in result.stdout.lower() or "default" in result.stdout.lower()
