"""Tests for octopus.core.sandbox — Sandbox."""

from __future__ import annotations

from pathlib import Path

from octopus.core.sandbox import OperationType, Sandbox


class TestSandbox:
    def test_validate_path_read_allowed(self) -> None:
        sb = Sandbox()
        result = sb.validate_path(Path("/tmp/test.py"), OperationType.READ)
        assert result.valid

    def test_validate_path_sensitive_blocked(self) -> None:
        sb = Sandbox()
        result = sb.validate_path(Path("~/.ssh/id_rsa"), OperationType.READ)
        assert not result.valid
        assert "sensitive" in (result.reason or "").lower()

    def test_validate_path_write_allowed_in_workspace(self) -> None:
        sb = Sandbox({"allowed_paths": ["/tmp/*"]})
        result = sb.validate_path(Path("/tmp/test.py"), OperationType.WRITE)
        assert result.valid

    def test_validate_path_write_blocked_outside_workspace(self) -> None:
        sb = Sandbox({"allowed_paths": ["/tmp/*"]})
        result = sb.validate_path(Path("/etc/passwd"), OperationType.WRITE)
        assert not result.valid

    def test_validate_command_safe(self) -> None:
        sb = Sandbox()
        result = sb.validate_command("ls -la /tmp")
        assert result.valid

    def test_validate_command_dangerous(self) -> None:
        sb = Sandbox()
        result = sb.validate_command("rm -rf /")
        assert not result.valid
        assert "dangerous" in (result.reason or "").lower()

    def test_validate_command_sudo(self) -> None:
        sb = Sandbox()
        result = sb.validate_command("sudo apt install something")
        assert not result.valid

    def test_disabled_sandbox_allows_all(self) -> None:
        sb = Sandbox({"enabled": False})
        result = sb.validate_path(Path("~/.ssh/id_rsa"), OperationType.READ)
        assert result.valid
        result = sb.validate_command("rm -rf /")
        assert result.valid

    def test_add_sensitive_path(self) -> None:
        sb = Sandbox()
        sb.add_sensitive_path("**/secret.key")
        result = sb.validate_path(Path("/project/secret.key"), OperationType.READ)
        assert not result.valid

    def test_add_allowed_path(self) -> None:
        sb = Sandbox()
        sb.add_allowed_path("/custom/workspace/*")
        result = sb.validate_path(
            Path("/custom/workspace/file.py"), OperationType.WRITE
        )
        assert result.valid
