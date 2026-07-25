"""Tests for octopus.providers — Provider protocol and LiteLLMProvider."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from octopus.loop.models import (
    Message,
    StreamEvent,
    StreamEventType,
    ToolCallDelta,
)


class MockProvider:
    """A mock provider that returns pre-configured responses."""

    def __init__(self, events: list[StreamEvent]) -> None:
        self._events = events

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        model: str,
        *,
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamEvent]:
        for event in self._events:
            yield event


class TestMockProvider:
    async def test_yields_text_events(self) -> None:
        provider = MockProvider(
            [
                StreamEvent(type=StreamEventType.TEXT, text="Hello "),
                StreamEvent(type=StreamEventType.TEXT, text="world"),
                StreamEvent(type=StreamEventType.DONE),
            ]
        )
        events = []
        async for e in provider.stream([], [], "test-model"):
            events.append(e)
        assert len(events) == 3
        assert events[0].text == "Hello "
        assert events[1].text == "world"
        assert events[2].type == StreamEventType.DONE

    async def test_yields_tool_call(self) -> None:
        tc = ToolCallDelta(id="call-1", name="read_file", arguments='{"path": "/tmp"}')
        provider = MockProvider(
            [
                StreamEvent(type=StreamEventType.TOOL_CALL, tool_call=tc),
                StreamEvent(type=StreamEventType.DONE),
            ]
        )
        events = []
        async for e in provider.stream([], [], "test-model"):
            events.append(e)
        assert events[0].tool_call is not None
        assert events[0].tool_call.name == "read_file"

    async def test_yields_usage(self) -> None:
        provider = MockProvider(
            [
                StreamEvent(
                    type=StreamEventType.USAGE,
                    usage={
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "total_tokens": 15,
                    },
                ),
                StreamEvent(type=StreamEventType.DONE),
            ]
        )
        events = []
        async for e in provider.stream([], [], "test-model"):
            events.append(e)
        assert events[0].usage is not None
        assert events[0].usage["total_tokens"] == 15

    async def test_yields_error(self) -> None:
        provider = MockProvider(
            [
                StreamEvent(type=StreamEventType.ERROR, error="API rate limited"),
                StreamEvent(type=StreamEventType.DONE),
            ]
        )
        events = []
        async for e in provider.stream([], [], "test-model"):
            events.append(e)
        assert events[0].error == "API rate limited"
