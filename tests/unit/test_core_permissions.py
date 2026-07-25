"""Tests for octopus.core.permissions — PermissionEngine."""

from __future__ import annotations

import pytest

from octopus.core.kernel import Context, PermissionMode, ToolCall
from octopus.core.permissions import PermissionEngine, PermissionResult


class TestPermissionEngine:
    def test_default_mode_allows_read(self) -> None:
        engine = PermissionEngine({"mode": "default"})
        tc = ToolCall(tool_name="read_file", arguments={"path": "/tmp/test.py"})
        ctx = Context(session_id="s1", permission_mode=PermissionMode.DEFAULT)
        result = engine.check(tc, ctx)
        assert result.allowed

    def test_default_mode_blocks_sensitive_path(self) -> None:
        engine = PermissionEngine({"mode": "default"})
        tc = ToolCall(tool_name="read_file", arguments={"path": "~/.ssh/id_rsa"})
        ctx = Context(session_id="s1", permission_mode=PermissionMode.DEFAULT)
        result = engine.check(tc, ctx)
        assert not result.allowed
        assert "sensitive" in (result.reason or "").lower()

    def test_full_auto_allows_everything(self) -> None:
        engine = PermissionEngine({"mode": "full_auto"})
        tc = ToolCall(tool_name="write_file", arguments={"path": "/tmp/test.py"})
        ctx = Context(session_id="s1", permission_mode=PermissionMode.FULL_AUTO)
        result = engine.check(tc, ctx)
        assert result.allowed

    def test_plan_blocks_writes(self) -> None:
        engine = PermissionEngine({"mode": "plan"})
        tc = ToolCall(tool_name="write_file", arguments={"path": "/tmp/test.py"})
        ctx = Context(session_id="s1", permission_mode=PermissionMode.PLAN)
        result = engine.check(tc, ctx)
        assert not result.allowed
        assert "plan mode" in (result.reason or "").lower()

    def test_dangerous_command_requires_approval(self) -> None:
        engine = PermissionEngine({"mode": "default"})
        tc = ToolCall(tool_name="shell", arguments={"command": "rm -rf /tmp/test"})
        ctx = Context(session_id="s1", permission_mode=PermissionMode.DEFAULT)
        result = engine.check(tc, ctx)
        assert result.requires_approval

    def test_safe_command_allowed(self) -> None:
        engine = PermissionEngine({"mode": "default"})
        tc = ToolCall(tool_name="shell", arguments={"command": "ls -la"})
        ctx = Context(session_id="s1", permission_mode=PermissionMode.DEFAULT)
        result = engine.check(tc, ctx)
        assert result.allowed

    def test_unknown_tool_allowed(self) -> None:
        engine = PermissionEngine({"mode": "default"})
        tc = ToolCall(tool_name="custom_tool", arguments={})
        ctx = Context(session_id="s1", permission_mode=PermissionMode.DEFAULT)
        result = engine.check(tc, ctx)
        assert result.allowed

    def test_custom_sensitive_path(self) -> None:
        engine = PermissionEngine({
            "mode": "default",
            "sensitive_paths": ["**/secret.key"],
        })
        tc = ToolCall(tool_name="read_file", arguments={"path": "/project/secret.key"})
        ctx = Context(session_id="s1", permission_mode=PermissionMode.DEFAULT)
        result = engine.check(tc, ctx)
        assert not result.allowed
