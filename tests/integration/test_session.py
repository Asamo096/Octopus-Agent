"""Integration tests for session persistence.

Tests session creation, message storage, resume, list, and delete.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from octopus.core.kernel import Kernel, PermissionMode
from octopus.loop.context import ConversationContext
from octopus.loop.models import Message, Role


@pytest.fixture
async def test_kernel(tmp_path: Path) -> Kernel:
    db_path = tmp_path / "test_session.db"
    k = Kernel(
        db_path=db_path,
        workspace=tmp_path,
        permission_mode=PermissionMode.FULL_AUTO,
    )
    await k.initialize()
    yield k
    await k.shutdown()


@pytest.mark.asyncio
async def test_create_and_resume_session(test_kernel: Kernel) -> None:
    """Create a session, add messages, save, reload, verify restored."""
    session_id = "test-session-resume"

    # Create
    ctx = ConversationContext(
        session_id=session_id,
        system_prompt="You are a test assistant.",
        model="test-model",
    )
    ctx.ensure_system_message()
    ctx.add_message(Message(role=Role.USER, content="First message"))
    ctx.add_message(
        Message(role=Role.ASSISTANT, content="First response")
    )

    await test_kernel.state.create_session(session_id, workspace="/tmp/test")
    await ctx.save(test_kernel.state)

    # Reload
    restored = await ConversationContext.load(session_id, test_kernel.state)
    assert restored is not None
    assert restored.session_id == session_id
    assert len(restored.messages) >= 3  # system + user + assistant
    assert any(
        m.role == Role.USER and "First message" in (m.content or "")
        for m in restored.messages
    )


@pytest.mark.asyncio
async def test_session_list(test_kernel: Kernel) -> None:
    """List all sessions sorted by recent activity."""
    for i in range(3):
        sid = f"session-{i}"
        await test_kernel.state.create_session(sid, workspace="/tmp")
        ctx = ConversationContext(
            session_id=sid,
            system_prompt="Test",
            model="test",
        )
        ctx.ensure_system_message()
        await ctx.save(test_kernel.state)

    sessions = await test_kernel.state.list_sessions()
    assert len(sessions) >= 3


@pytest.mark.asyncio
async def test_session_delete(test_kernel: Kernel) -> None:
    """Delete a session and verify it's gone."""
    sid = "session-to-delete"
    await test_kernel.state.create_session(sid, workspace="/tmp")
    ctx = ConversationContext(session_id=sid, system_prompt="Test", model="test")
    ctx.ensure_system_message()
    await ctx.save(test_kernel.state)

    # Verify it exists
    restored = await ConversationContext.load(sid, test_kernel.state)
    assert restored is not None

    # Delete and verify gone
    await test_kernel.state.delete_session(sid)
    restored2 = await ConversationContext.load(sid, test_kernel.state)
    assert restored2 is None


@pytest.mark.asyncio
async def test_resume_nonexistent_returns_none(test_kernel: Kernel) -> None:
    """Loading a nonexistent session returns None."""
    result = await ConversationContext.load("nonexistent-id-xyz", test_kernel.state)
    assert result is None


@pytest.mark.asyncio
async def test_conversation_sanitize_removes_orphan_tool_calls(
    test_kernel: Kernel,
) -> None:
    """Sanitize removes orphan tool results without matching tool calls."""
    ctx = ConversationContext(
        session_id="test-sanitize",
        system_prompt="Test",
        model="test",
    )
    ctx.ensure_system_message()
    ctx.add_message(Message(role=Role.USER, content="Hello"))
    # Add an orphaned tool result (no matching tool call)
    ctx.add_message(
        Message(role=Role.TOOL, content="orphan result", tool_call_id="orphan_1")
    )

    ctx.sanitize()
    # Orphan tool result should be removed
    tool_msgs = [m for m in ctx.messages if m.role == Role.TOOL]
    assert len(tool_msgs) == 0
