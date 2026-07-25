"""Tests for CompactionEngine — conversation compaction strategies."""

from __future__ import annotations

from octopus.loop.compaction import (
    CompactionEngine,
    session_memory_compact_prompt,
)
from octopus.loop.context import ConversationContext
from octopus.loop.models import Message, Role, ToolCallDelta


def _make_context_with_tokens(
    n_messages: int, chars_per_msg: int = 400
) -> ConversationContext:
    """Helper: create a context with roughly predictable token count."""
    ctx = ConversationContext(session_id="test-1", system_prompt="System.")
    ctx.ensure_system_message()
    for i in range(n_messages):
        role = Role.USER if i % 2 == 0 else Role.ASSISTANT
        ctx.add_message(Message(role=role, content="x" * chars_per_msg))
    return ctx


class TestMicrocompact:
    """Microcompact: clear old tool result content."""

    def test_short_conversation_noop(self) -> None:
        ctx = ConversationContext(session_id="test-1")
        ctx.add_message(Message(role=Role.SYSTEM, content="System."))
        ctx.add_message(Message(role=Role.USER, content="hello"))
        ctx.add_message(Message(role=Role.ASSISTANT, content="hi"))

        engine = CompactionEngine()
        removed = engine.microcompact(ctx)
        assert removed == 0
        assert ctx.messages[2].content == "hi"

    def test_clears_old_tool_results(self) -> None:
        ctx = ConversationContext(session_id="test-1")
        ctx.add_message(Message(role=Role.SYSTEM, content="System."))

        # Add 10 tool result messages (old ones should be cleared)
        for i in range(10):
            ctx.add_message(
                Message(
                    role=Role.TOOL,
                    content="x" * 3000,  # Large tool result
                    tool_call_id=f"tc_{i}",
                )
            )
        # Recent messages (last 8) should be preserved
        ctx.add_message(Message(role=Role.USER, content="latest"))
        ctx.add_message(Message(role=Role.ASSISTANT, content="response"))

        engine = CompactionEngine(max_inline_tool_result=2000)
        removed = engine.microcompact(ctx)

        # Should have cleared some old tool results
        assert removed > 0
        # The cleared messages should have truncated content
        for msg in ctx.messages[1 : 1 + (10 - 8)]:
            if msg.role == Role.TOOL:
                assert "truncated" in msg.content

    def test_preserves_recent_messages(self) -> None:
        ctx = ConversationContext(session_id="test-1")
        ctx.add_message(Message(role=Role.SYSTEM, content="System."))

        # Add 10 tool results
        for i in range(10):
            ctx.add_message(
                Message(
                    role=Role.TOOL,
                    content="x" * 3000,
                    tool_call_id=f"tc_{i}",
                )
            )

        engine = CompactionEngine(max_inline_tool_result=2000)
        engine.microcompact(ctx)

        # Last 8 tool results should be unchanged
        for msg in ctx.messages[-8:]:
            if msg.role == Role.TOOL:
                assert len(msg.content) == 3000


class TestContextCollapse:
    """Context collapse: truncate oversized text blocks."""

    def test_short_messages_unchanged(self) -> None:
        ctx = ConversationContext(session_id="test-1")
        ctx.add_message(Message(role=Role.USER, content="short message"))

        engine = CompactionEngine(context_collapse_max=5000)
        collapsed = engine.context_collapse(ctx)
        assert collapsed == 0
        assert ctx.messages[0].content == "short message"

    def test_long_messages_truncated(self) -> None:
        ctx = ConversationContext(session_id="test-1")
        long_text = "x" * 10000
        ctx.add_message(Message(role=Role.USER, content=long_text))

        engine = CompactionEngine(context_collapse_max=5000)
        collapsed = engine.context_collapse(ctx)

        assert collapsed == 1
        assert len(ctx.messages[0].content) < 10000
        assert "truncated" in ctx.messages[0].content

    def test_preserves_start_and_end(self) -> None:
        ctx = ConversationContext(session_id="test-1")
        long_text = "START" + "x" * 10000 + "END"
        ctx.add_message(Message(role=Role.ASSISTANT, content=long_text))

        engine = CompactionEngine(context_collapse_max=5000)
        engine.context_collapse(ctx)

        # Should keep start and end
        assert ctx.messages[0].content.startswith("START")
        assert ctx.messages[0].content.endswith("END")

    def test_only_truncates_user_assistant(self) -> None:
        ctx = ConversationContext(session_id="test-1")
        ctx.add_message(Message(role=Role.TOOL, content="x" * 10000))

        engine = CompactionEngine(context_collapse_max=5000)
        collapsed = engine.context_collapse(ctx)

        # Tool messages should not be collapsed
        assert collapsed == 0
        assert len(ctx.messages[0].content) == 10000


class TestAutoCompact:
    """Auto-compact: automatic strategy selection."""

    def test_under_threshold_noop(self) -> None:
        ctx = _make_context_with_tokens(5, 100)  # ~125 tokens
        engine = CompactionEngine(auto_compact_threshold=80000)

        result = engine.auto_compact(ctx)
        assert not result.compacted
        assert result.tokens_before == result.tokens_after

    def test_microcompact_for_small_overflow(self) -> None:
        # Create a context with large tool results that will overflow
        ctx = ConversationContext(session_id="test-1", system_prompt="System.")
        ctx.ensure_system_message()

        # Add old tool results that can be microcompacted
        for i in range(20):
            ctx.add_message(
                Message(
                    role=Role.TOOL,
                    content="x" * 5000,  # ~1250 tokens each
                    tool_call_id=f"tc_{i}",
                )
            )
        ctx.add_message(Message(role=Role.USER, content="hello"))
        ctx.add_message(Message(role=Role.ASSISTANT, content="hi"))

        engine = CompactionEngine(
            auto_compact_threshold=1000,  # Low threshold to trigger
            max_inline_tool_result=500,
        )
        result = engine.auto_compact(ctx)

        assert result.compacted
        assert result.tokens_after < result.tokens_before

    def test_context_collapse_for_medium_overflow(self) -> None:
        # Create context with large text blocks
        ctx = ConversationContext(session_id="test-1", system_prompt="System.")
        ctx.ensure_system_message()

        # Add large assistant/user messages
        for i in range(10):
            ctx.add_message(
                Message(
                    role=Role.ASSISTANT if i % 2 else Role.USER,
                    content="x" * 20000,  # ~5000 tokens each
                )
            )

        engine = CompactionEngine(
            auto_compact_threshold=5000,
            context_collapse_max=2000,
        )
        result = engine.auto_compact(ctx)

        assert result.compacted
        assert result.tokens_after < result.tokens_before


class TestReactiveCompact:
    """Reactive compaction on prompt-too-long errors."""

    def test_reduces_token_count(self) -> None:
        ctx = _make_context_with_tokens(20, 5000)

        engine = CompactionEngine(context_collapse_max=2000)
        result = engine.reactive_compact(ctx, "prompt is too long")

        assert result.compacted
        assert result.tokens_after < result.tokens_before


class TestSessionMemoryPrompt:
    """Session memory compaction prompt generation."""

    def test_generates_valid_prompt(self) -> None:
        messages = [
            Message(role=Role.SYSTEM, content="You are helpful."),
            Message(role=Role.USER, content="Write a sorting algorithm."),
            Message(role=Role.ASSISTANT, content="Here's a quicksort..."),
        ]
        prompt = session_memory_compact_prompt(messages)

        assert "summarize" in prompt.lower()
        assert "sorting algorithm" in prompt
        assert "quicksort" in prompt

    def test_includes_tool_info(self) -> None:
        tc = ToolCallDelta(id="tc1", name="write_file", arguments="{}")
        messages = [
            Message(role=Role.ASSISTANT, content="Writing file...", tool_calls=[tc]),
            Message(role=Role.TOOL, content="File written.", tool_call_id="tc1"),
        ]
        prompt = session_memory_compact_prompt(messages)

        assert "write_file" in prompt
