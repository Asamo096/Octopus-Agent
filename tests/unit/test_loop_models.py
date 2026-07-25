"""Tests for octopus.loop.models — Message, StreamEvent, etc."""

from __future__ import annotations

from octopus.loop.models import (
    Message,
    Role,
    StreamEvent,
    StreamEventType,
    ToolCallDelta,
)


class TestMessage:
    def test_user_message_to_dict(self) -> None:
        msg = Message(role=Role.USER, content="Hello")
        d = msg.to_dict()
        assert d == {"role": "user", "content": "Hello"}

    def test_assistant_message_with_tool_calls(self) -> None:
        tc = ToolCallDelta(id="call-1", name="read_file", arguments='{"path": "/tmp"}')
        msg = Message(role=Role.ASSISTANT, content=None, tool_calls=[tc])
        d = msg.to_dict()
        assert d["role"] == "assistant"
        assert d["tool_calls"][0]["id"] == "call-1"
        assert d["tool_calls"][0]["function"]["name"] == "read_file"

    def test_tool_result_message(self) -> None:
        msg = Message(
            role=Role.TOOL,
            content='{"output": "ok"}',
            tool_call_id="call-1",
            name="read_file",
        )
        d = msg.to_dict()
        assert d["role"] == "tool"
        assert d["tool_call_id"] == "call-1"
        assert d["name"] == "read_file"

    def test_system_message(self) -> None:
        msg = Message(role=Role.SYSTEM, content="You are helpful.")
        d = msg.to_dict()
        assert d == {"role": "system", "content": "You are helpful."}

    def test_message_with_none_content(self) -> None:
        msg = Message(role=Role.ASSISTANT, content=None)
        d = msg.to_dict()
        assert "content" not in d


class TestStreamEvent:
    def test_text_event(self) -> None:
        e = StreamEvent(type=StreamEventType.TEXT, text="hello")
        assert e.type == StreamEventType.TEXT
        assert e.text == "hello"

    def test_tool_call_event(self) -> None:
        tc = ToolCallDelta(id="c1", name="shell", arguments='{"command": "ls"}')
        e = StreamEvent(type=StreamEventType.TOOL_CALL, tool_call=tc)
        assert e.tool_call is not None
        assert e.tool_call.name == "shell"

    def test_usage_event(self) -> None:
        e = StreamEvent(type=StreamEventType.USAGE, usage={"total_tokens": 100})
        assert e.usage is not None
        assert e.usage["total_tokens"] == 100

    def test_error_event(self) -> None:
        e = StreamEvent(type=StreamEventType.ERROR, error="boom")
        assert e.error == "boom"

    def test_done_event(self) -> None:
        e = StreamEvent(type=StreamEventType.DONE)
        assert e.type == StreamEventType.DONE
