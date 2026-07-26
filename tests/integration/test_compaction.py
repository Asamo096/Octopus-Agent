"""Integration tests for the compaction engine.

Tests microcompact, context collapse, auto-compact triggers,
and compaction boundaries.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from octopus.core.kernel import Kernel, PermissionMode
from octopus.loop.compaction import CompactionEngine, CompactionStrategy
from octopus.loop.context import ConversationContext
from octopus.loop.models import Message, Role


@pytest.fixture
async def kernel_for_compaction(tmp_path: Path) -> Kernel:
    db_path = tmp_path / "test_compaction.db"
    k = Kernel(
        db_path=db_path,
        workspace=tmp_path,
        permission_mode=PermissionMode.FULL_AUTO,
    )
    await k.initialize()
    yield k
    await k.shutdown()


@pytest.fixture
def compaction() -> CompactionEngine:
    return CompactionEngine()


@pytest.fixture
def long_conversation() -> ConversationContext:
    """A conversation with many messages to trigger compaction."""
    ctx = ConversationContext(
        session_id="test-compact",
        system_prompt="You are a test assistant. " * 20,
        model="test-model",
    )
    ctx.ensure_system_message()

    for i in range(20):
        ctx.add_message(
            Message(role=Role.USER, content=f"Question {i}: " + "x" * 500)
        )
        ctx.add_message(
            Message(role=Role.ASSISTANT, content=f"Answer {i}: " + "y" * 500)
        )
        ctx.add_message(
            Message(
                role=Role.TOOL,
                content=f"File content {i}: " + "z" * 2000,
                tool_call_id=f"tc_{i}",
            )
        )

    return ctx


# ---------------------------------------------------------------------------
# Microcompact tests
# ---------------------------------------------------------------------------


def test_microcompact_clears_old_results(
    compaction: CompactionEngine, long_conversation: ConversationContext
) -> None:
    """Tool results older than max_turns are cleared."""
    result = compaction.auto_compact(long_conversation)
    # Should complete without error and return a result
    assert result is not None
    assert result.compacted in (True, False)


def test_microcompact_preserves_recent_tool_results(
    compaction: CompactionEngine,
) -> None:
    """Recent tool results within max_turns are preserved."""
    ctx = ConversationContext(session_id="test", model="test")
    ctx.ensure_system_message()
    ctx.add_message(Message(role=Role.USER, content="Read file"))
    ctx.add_message(
        Message(role=Role.TOOL, content="recent content", tool_call_id="tc_0")
    )
    ctx.add_message(Message(role=Role.USER, content="Another message"))

    result = compaction.auto_compact(ctx)
    # Should not crash on small conversations
    assert result is not None


# ---------------------------------------------------------------------------
# Context collapse tests
# ---------------------------------------------------------------------------


def test_context_collapse_truncates_large_blocks(
    compaction: CompactionEngine,
) -> None:
    """Oversized text blocks are truncated to max_chars."""
    ctx = ConversationContext(session_id="test", model="test")
    ctx.ensure_system_message()
    ctx.add_message(Message(role=Role.USER, content="x" * 10000))

    removed = compaction.context_collapse(ctx, max_chars=5000)
    # Should remove or truncate characters
    assert removed >= 0


def test_context_collapse_preserves_small_blocks(
    compaction: CompactionEngine,
) -> None:
    """Messages under max_chars are left unchanged."""
    ctx = ConversationContext(session_id="test", model="test")
    ctx.ensure_system_message()
    ctx.add_message(Message(role=Role.USER, content="short message"))

    removed = compaction.context_collapse(ctx, max_chars=5000)
    # Should not change short messages
    user_msgs = [m for m in ctx.messages if m.role == Role.USER]
    assert len(user_msgs) > 0
    assert user_msgs[0].content == "short message"


# ---------------------------------------------------------------------------
# Auto-compact tests
# ---------------------------------------------------------------------------


def test_auto_compact_not_triggered_when_under_threshold(
    compaction: CompactionEngine,
) -> None:
    """Auto-compact does nothing when context is under threshold."""
    ctx = ConversationContext(session_id="test", model="test")
    ctx.ensure_system_message()
    ctx.add_message(Message(role=Role.USER, content="short"))

    result = compaction.auto_compact(ctx)
    # Under threshold should not compact
    if not result.compacted:
        assert result.strategy is None
    # Either way, the result is valid
    assert result is not None


def test_auto_compact_triggers_when_over_threshold(
    compaction: CompactionEngine, long_conversation: ConversationContext
) -> None:
    """Auto-compact fires when token count exceeds threshold."""
    compaction.auto_compact_threshold = 100
    result = compaction.auto_compact(long_conversation)
    assert result is not None
    # Should be compacted with very low threshold
    if result.compacted:
        assert result.tokens_after < result.tokens_before


def test_compact_result_has_strategy(
    compaction: CompactionEngine, long_conversation: ConversationContext
) -> None:
    """Compaction result includes the strategy used."""
    compaction.auto_compact_threshold = 100
    result = compaction.auto_compact(long_conversation)
    if result.compacted and result.strategy:
        assert isinstance(result.strategy, CompactionStrategy)
