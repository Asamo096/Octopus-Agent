"""Tests for octopus.core.kernel — Kernel, Context, ToolCall, ToolResult."""

from __future__ import annotations

from octopus.core.kernel import Context, Kernel, PermissionMode, ToolCall, ToolResult


class TestToolCall:
    def test_create(self) -> None:
        tc = ToolCall(tool_name="read_file", arguments={"path": "/tmp/test.py"})
        assert tc.tool_name == "read_file"
        assert tc.arguments == {"path": "/tmp/test.py"}
        assert tc.call_id is None

    def test_with_call_id(self) -> None:
        tc = ToolCall(tool_name="shell", arguments={"command": "ls"}, call_id="call-1")
        assert tc.call_id == "call-1"


class TestToolResult:
    def test_success(self) -> None:
        r = ToolResult(success=True, output="ok")
        assert r.success
        assert r.output == "ok"
        assert r.error is None

    def test_failure(self) -> None:
        r = ToolResult(success=False, output=None, error="denied")
        assert not r.success
        assert r.error == "denied"


class TestContext:
    def test_defaults(self) -> None:
        ctx = Context(session_id="s1")
        assert ctx.session_id == "s1"
        assert ctx.kernel is None
        assert ctx.workspace is None
        assert ctx.permission_mode == PermissionMode.DEFAULT

    def test_with_kernel(self, kernel: Kernel) -> None:
        ctx = Context(session_id="s1", kernel=kernel)
        assert ctx.kernel is kernel


class TestKernel:
    async def test_initialize(self, kernel: Kernel) -> None:
        assert kernel._initialized
        assert kernel.permissions is not None
        assert kernel.audit is not None
        assert kernel.sandbox is not None
        assert kernel.hooks is not None
        assert kernel.state is not None

    async def test_register_and_get_tool(self, kernel: Kernel) -> None:
        class DummyTool:
            name = "dummy"
            description = "A dummy tool"

            async def execute(self, args, ctx):
                return ToolResult(success=True, output="dummy result")

        kernel.register_tool(DummyTool())
        assert kernel.get_tool("dummy") is not None
        assert kernel.get_tool("nonexistent") is None

    async def test_list_tools(self, kernel: Kernel) -> None:
        class ToolA:
            name = "a"
            description = "tool A"

            async def execute(self, args, ctx):
                return ToolResult(success=True, output="a")

        class ToolB:
            name = "b"
            description = "tool B"

            async def execute(self, args, ctx):
                return ToolResult(success=True, output="b")

        kernel.register_tool(ToolA())
        kernel.register_tool(ToolB())
        tools = kernel.list_tools()
        names = {t["name"] for t in tools}
        assert "a" in names
        assert "b" in names

    async def test_execute_tool_not_found(self, kernel: Kernel, ctx: Context) -> None:
        tc = ToolCall(tool_name="nonexistent", arguments={})
        result = await kernel.execute_tool(tc, ctx)
        assert not result.success
        assert "not found" in (result.error or "").lower()

    async def test_execute_tool_success(self, kernel: Kernel, ctx: Context) -> None:
        class EchoTool:
            name = "echo"
            description = "Echo tool"

            async def execute(self, args, ctx):
                return ToolResult(success=True, output=args.get("text", ""))

        kernel.register_tool(EchoTool())
        tc = ToolCall(tool_name="echo", arguments={"text": "hello"})
        result = await kernel.execute_tool(tc, ctx)
        assert result.success
        assert result.output == "hello"

    async def test_execute_tool_exception(self, kernel: Kernel, ctx: Context) -> None:
        class BadTool:
            name = "bad"
            description = "Always raises"

            async def execute(self, args, ctx):
                raise RuntimeError("boom")

        kernel.register_tool(BadTool())
        tc = ToolCall(tool_name="bad", arguments={})
        result = await kernel.execute_tool(tc, ctx)
        assert not result.success
        assert "boom" in (result.error or "")

    async def test_audit_logged(self, kernel: Kernel, ctx: Context) -> None:
        class EchoTool:
            name = "echo2"
            description = "Echo tool"

            async def execute(self, args, ctx):
                return ToolResult(success=True, output="ok")

        kernel.register_tool(EchoTool())
        tc = ToolCall(tool_name="echo2", arguments={"text": "test"})
        await kernel.execute_tool(tc, ctx)

        events = await kernel.audit.get_by_tool("echo2")
        assert len(events) >= 1
        assert events[0].tool == "echo2"
        assert events[0].permission_decision == "ALLOWED"
