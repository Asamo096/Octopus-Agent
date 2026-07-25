"""Tests for octopus.loop.engine — the agent loop."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from octopus.core.kernel import Context, Kernel, PermissionMode
from octopus.loop.engine import run_query
from octopus.loop.models import (
    Message,
    Role,
    StreamEvent,
    StreamEventType,
    ToolCallDelta,
)
from octopus.tools.base import ToolRegistry
from octopus.tools.filesystem import ReadFileTool, WriteFileTool
from octopus.tools.shell import ShellTool

# ---------------------------------------------------------------------------
# Mock provider helpers
# ---------------------------------------------------------------------------


class TextOnlyProvider:
    """Returns a simple text response with no tool calls."""

    def __init__(self, text: str) -> None:
        self._text = text

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        model: str,
        *,
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamEvent]:
        yield StreamEvent(type=StreamEventType.TEXT, text=self._text)
        yield StreamEvent(type=StreamEventType.DONE)


class ToolThenTextProvider:
    """First returns a tool call, then text."""

    def __init__(self, tool_name: str, tool_args: str, final_text: str) -> None:
        self._tool_name = tool_name
        self._tool_args = tool_args
        self._final_text = final_text
        self._call_count = 0

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        model: str,
        *,
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamEvent]:
        self._call_count += 1
        if self._call_count == 1:
            # First call: return a tool call
            yield StreamEvent(
                type=StreamEventType.TOOL_CALL,
                tool_call=ToolCallDelta(
                    id="call-1", name=self._tool_name, arguments=self._tool_args
                ),
            )
            yield StreamEvent(type=StreamEventType.DONE)
        else:
            # Second call: return text
            yield StreamEvent(type=StreamEventType.TEXT, text=self._final_text)
            yield StreamEvent(type=StreamEventType.DONE)


class ErrorProvider:
    """Returns an error."""

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        model: str,
        *,
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamEvent]:
        yield StreamEvent(type=StreamEventType.ERROR, error="API error")
        yield StreamEvent(type=StreamEventType.DONE)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(ReadFileTool())
    reg.register(WriteFileTool())
    reg.register(ShellTool())
    return reg


@pytest.fixture
def ctx(kernel: Kernel, tmp_path: Path) -> Context:
    return Context(
        session_id="test",
        kernel=kernel,
        workspace=tmp_path,
        permission_mode=PermissionMode.FULL_AUTO,
    )


class TestRunQuery:
    async def test_text_only_response(
        self, kernel: Kernel, registry: ToolRegistry, ctx: Context
    ) -> None:
        provider = TextOnlyProvider("Hello, world!")
        messages = [Message(role=Role.USER, content="Hi")]

        events = []
        async for e in run_query(
            messages, provider, kernel, registry, ctx, model="test"
        ):
            events.append(e)

        # Should have TEXT + DONE
        text_events = [e for e in events if e.type == StreamEventType.TEXT]
        done_events = [e for e in events if e.type == StreamEventType.DONE]
        assert len(text_events) == 1
        assert text_events[0].text == "Hello, world!"
        assert len(done_events) == 1

        # Messages should have user + assistant
        assert len(messages) == 2
        assert messages[0].role == Role.USER
        assert messages[1].role == Role.ASSISTANT
        assert messages[1].content == "Hello, world!"

    async def test_tool_call_then_text(
        self, kernel: Kernel, registry: ToolRegistry, ctx: Context, tmp_path: Path
    ) -> None:
        # Create a file for the tool to read
        (tmp_path / "test.txt").write_text("file content")

        provider = ToolThenTextProvider(
            tool_name="read_file",
            tool_args='{"path": "test.txt"}',
            final_text="I read the file.",
        )
        messages = [Message(role=Role.USER, content="Read test.txt")]

        events = []
        async for e in run_query(
            messages, provider, kernel, registry, ctx, model="test"
        ):
            events.append(e)

        text_events = [e for e in events if e.type == StreamEventType.TEXT]
        tool_events = [e for e in events if e.type == StreamEventType.TOOL_CALL]
        done_events = [e for e in events if e.type == StreamEventType.DONE]

        assert len(tool_events) >= 1
        assert len(text_events) >= 1
        assert len(done_events) == 1

        # Messages: user, assistant (with tool_call), tool result, assistant (final)
        assert len(messages) == 4
        assert messages[0].role == Role.USER
        assert messages[1].role == Role.ASSISTANT
        assert messages[2].role == Role.TOOL
        assert messages[3].role == Role.ASSISTANT
        assert messages[3].content == "I read the file."

    async def test_error_stops_loop(
        self, kernel: Kernel, registry: ToolRegistry, ctx: Context
    ) -> None:
        provider = ErrorProvider()
        messages = [Message(role=Role.USER, content="test")]

        events = []
        async for e in run_query(
            messages, provider, kernel, registry, ctx, model="test"
        ):
            events.append(e)

        error_events = [e for e in events if e.type == StreamEventType.ERROR]
        done_events = [e for e in events if e.type == StreamEventType.DONE]
        assert len(error_events) == 1
        assert error_events[0].error == "API error"
        assert len(done_events) == 1

    async def test_max_turns_enforced(
        self, kernel: Kernel, registry: ToolRegistry, ctx: Context, tmp_path: Path
    ) -> None:
        # Provider that always returns a tool call
        class AlwaysToolProvider:
            async def stream(self, messages, tools, model, **kwargs):
                yield StreamEvent(
                    type=StreamEventType.TOOL_CALL,
                    tool_call=ToolCallDelta(
                        id="c1",
                        name="read_file",
                        arguments='{"path": "nonexistent.txt"}',
                    ),
                )
                yield StreamEvent(type=StreamEventType.DONE)

        provider = AlwaysToolProvider()
        messages = [Message(role=Role.USER, content="test")]

        events = []
        async for e in run_query(
            messages, provider, kernel, registry, ctx, model="test", max_turns=3
        ):
            events.append(e)

        error_events = [e for e in events if e.type == StreamEventType.ERROR]
        assert len(error_events) == 1
        assert "max turns" in error_events[0].error.lower()
