"""Tests for octopus.tools.base — ToolRegistry."""

from __future__ import annotations

from typing import Any

from octopus.core.kernel import Context, ToolResult
from octopus.tools.base import ToolRegistry


class DummyTool:
    name = "dummy"
    description = "A dummy tool for testing"
    input_schema = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }

    async def execute(self, args: dict[str, Any], ctx: Context) -> ToolResult:
        return ToolResult(success=True, output=args.get("text", ""))


class AnotherTool:
    name = "another"
    description = "Another tool"
    input_schema = {"type": "object", "properties": {}}

    async def execute(self, args: dict[str, Any], ctx: Context) -> ToolResult:
        return ToolResult(success=True, output="another")


class TestToolRegistry:
    def test_register_and_get(self) -> None:
        reg = ToolRegistry()
        reg.register(DummyTool())
        assert reg.get("dummy") is not None
        assert reg.get("nonexistent") is None

    def test_list_names(self) -> None:
        reg = ToolRegistry()
        reg.register(DummyTool())
        reg.register(AnotherTool())
        names = reg.list_names()
        assert "dummy" in names
        assert "another" in names

    def test_list_definitions(self) -> None:
        reg = ToolRegistry()
        reg.register(DummyTool())
        defs = reg.list_definitions()
        assert len(defs) == 1
        assert defs[0]["type"] == "function"
        assert defs[0]["function"]["name"] == "dummy"
        assert defs[0]["function"]["parameters"] == DummyTool.input_schema

    def test_len(self) -> None:
        reg = ToolRegistry()
        assert len(reg) == 0
        reg.register(DummyTool())
        assert len(reg) == 1

    def test_contains(self) -> None:
        reg = ToolRegistry()
        reg.register(DummyTool())
        assert "dummy" in reg
        assert "nonexistent" not in reg
