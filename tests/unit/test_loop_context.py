"""Tests for ConversationContext — message history management and persistence."""

from __future__ import annotations

from octopus.loop.context import ConversationContext
from octopus.loop.models import Message, Role, ToolCallDelta


class TestConversationContextBasic:
    """Basic message management operations."""

    def test_create_empty_context(self) -> None:
        ctx = ConversationContext(session_id="test-1")
        assert ctx.session_id == "test-1"
        assert ctx.messages == []
        assert ctx.system_prompt == ""

    def test_add_message(self) -> None:
        ctx = ConversationContext(session_id="test-1")
        ctx.add_message(Message(role=Role.USER, content="hello"))
        assert len(ctx.messages) == 1
        assert ctx.messages[0].content == "hello"

    def test_get_messages_returns_copy(self) -> None:
        ctx = ConversationContext(session_id="test-1")
        ctx.add_message(Message(role=Role.USER, content="hello"))
        msgs = ctx.get_messages()
        msgs.append(Message(role=Role.ASSISTANT, content="world"))
        assert len(ctx.messages) == 1  # Original unchanged

    def test_clear(self) -> None:
        ctx = ConversationContext(session_id="test-1")
        ctx.add_message(Message(role=Role.USER, content="hello"))
        ctx.add_message(Message(role=Role.ASSISTANT, content="world"))
        ctx.clear()
        assert ctx.messages == []

    def test_set_system_prompt_empty(self) -> None:
        ctx = ConversationContext(session_id="test-1", system_prompt="You are helpful.")
        ctx.set_system_prompt("New prompt.")
        assert ctx.system_prompt == "New prompt."
        assert ctx.messages[0].role == Role.SYSTEM
        assert ctx.messages[0].content == "New prompt."

    def test_set_system_prompt_existing(self) -> None:
        ctx = ConversationContext(session_id="test-1")
        ctx.messages = [Message(role=Role.SYSTEM, content="Old prompt.")]
        ctx.set_system_prompt("New prompt.")
        assert ctx.messages[0].content == "New prompt."

    def test_ensure_system_message_adds_if_missing(self) -> None:
        ctx = ConversationContext(session_id="test-1", system_prompt="System.")
        ctx.messages = [Message(role=Role.USER, content="hello")]
        ctx.ensure_system_message()
        assert ctx.messages[0].role == Role.SYSTEM
        assert len(ctx.messages) == 2

    def test_ensure_system_message_noop_if_present(self) -> None:
        ctx = ConversationContext(session_id="test-1", system_prompt="System.")
        ctx.messages = [Message(role=Role.SYSTEM, content="System.")]
        ctx.ensure_system_message()
        assert len(ctx.messages) == 1


class TestTokenEstimation:
    """Token estimation heuristics."""

    def test_empty_context(self) -> None:
        ctx = ConversationContext(session_id="test-1")
        assert ctx.estimate_tokens() == 0

    def test_single_message(self) -> None:
        ctx = ConversationContext(session_id="test-1")
        ctx.add_message(Message(role=Role.USER, content="a" * 400))
        # 400 chars / 4 chars_per_token = 100 tokens
        assert ctx.estimate_tokens() == 100

    def test_multiple_messages(self) -> None:
        ctx = ConversationContext(session_id="test-1")
        ctx.add_message(Message(role=Role.USER, content="a" * 200))
        ctx.add_message(Message(role=Role.ASSISTANT, content="b" * 200))
        # 400 chars / 4 = 100 tokens
        assert ctx.estimate_tokens() == 100

    def test_tool_calls_counted(self) -> None:
        ctx = ConversationContext(session_id="test-1")
        tc = ToolCallDelta(
            id="tc1", name="read_file", arguments='{"path": "/tmp/test.py"}'
        )
        ctx.add_message(Message(role=Role.ASSISTANT, content=None, tool_calls=[tc]))
        # name (9) + arguments (26) = 35 chars / 4 = 8 tokens
        assert ctx.estimate_tokens() == 8


class TestSerialization:
    """Serialization to/from dict for persistence."""

    def test_to_dict_basic(self) -> None:
        ctx = ConversationContext(
            session_id="test-1",
            system_prompt="System.",
            model="claude-sonnet-4-20250514",
        )
        ctx.add_message(Message(role=Role.USER, content="hello"))
        data = ctx.to_dict()
        assert data["session_id"] == "test-1"
        assert data["system_prompt"] == "System."
        assert len(data["messages"]) == 1
        assert data["messages"][0]["role"] == "user"

    def test_roundtrip(self) -> None:
        ctx = ConversationContext(session_id="test-1", system_prompt="System.")
        ctx.add_message(Message(role=Role.USER, content="hello"))
        ctx.add_message(Message(role=Role.ASSISTANT, content="hi there"))

        data = ctx.to_dict()
        restored = ConversationContext.from_dict(data)

        assert restored.session_id == ctx.session_id
        assert restored.system_prompt == ctx.system_prompt
        assert len(restored.messages) == 2
        assert restored.messages[0].content == "hello"
        assert restored.messages[1].content == "hi there"

    def test_roundtrip_with_tool_calls(self) -> None:
        ctx = ConversationContext(session_id="test-1")
        tc = ToolCallDelta(
            id="tc1", name="read_file", arguments='{"path": "/tmp/x.py"}'
        )
        ctx.add_message(Message(role=Role.ASSISTANT, content=None, tool_calls=[tc]))
        ctx.add_message(
            Message(
                role=Role.TOOL,
                content="file contents here",
                tool_call_id="tc1",
                name="read_file",
            )
        )

        data = ctx.to_dict()
        restored = ConversationContext.from_dict(data)

        assert len(restored.messages) == 2
        assert restored.messages[0].tool_calls is not None
        assert restored.messages[0].tool_calls[0].name == "read_file"
        assert restored.messages[1].tool_call_id == "tc1"


class TestSanitization:
    """Message sanitization after loading from persistence."""

    def test_drops_empty_assistant_messages(self) -> None:
        ctx = ConversationContext(session_id="test-1")
        ctx.messages = [
            Message(role=Role.SYSTEM, content="System."),
            Message(role=Role.ASSISTANT, content=None),  # Empty
            Message(role=Role.USER, content="hello"),
        ]
        ctx.sanitize()
        assert len(ctx.messages) == 2
        assert ctx.messages[0].role == Role.SYSTEM
        assert ctx.messages[1].role == Role.USER

    def test_keeps_assistant_with_tool_calls(self) -> None:
        ctx = ConversationContext(session_id="test-1")
        tc = ToolCallDelta(id="tc1", name="bash", arguments='{"command": "ls"}')
        ctx.messages = [
            Message(role=Role.SYSTEM, content="System."),
            Message(role=Role.ASSISTANT, content=None, tool_calls=[tc]),
            Message(role=Role.TOOL, content="file.txt", tool_call_id="tc1"),
        ]
        ctx.sanitize()
        assert len(ctx.messages) == 3

    def test_drops_orphan_tool_results(self) -> None:
        ctx = ConversationContext(session_id="test-1")
        ctx.messages = [
            Message(role=Role.SYSTEM, content="System."),
            Message(
                role=Role.TOOL, content="orphan result", tool_call_id="nonexistent"
            ),
        ]
        ctx.sanitize()
        # Orphan tool result should be dropped
        assert len(ctx.messages) == 1
        assert ctx.messages[0].role == Role.SYSTEM

    def test_ensures_system_message_at_start(self) -> None:
        ctx = ConversationContext(session_id="test-1", system_prompt="System prompt.")
        ctx.messages = [
            Message(role=Role.USER, content="hello"),
        ]
        ctx.sanitize()
        assert ctx.messages[0].role == Role.SYSTEM

    def test_empty_messages_noop(self) -> None:
        ctx = ConversationContext(session_id="test-1")
        ctx.sanitize()
        assert ctx.messages == []
