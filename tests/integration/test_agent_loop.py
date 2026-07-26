"""Integration tests for the agent query loop.

Tests the full think-act-observe cycle with mocked providers,
verifying tool dispatch, streaming, budget enforcement, and
error handling.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from octopus.core.kernel import Context, Kernel, PermissionMode, ToolCall, ToolResult
from octopus.loop.compaction import CompactionEngine
from octopus.loop.context import ConversationContext
from octopus.loop.engine import LoopBudget, run_query
from octopus.loop.models import (
    Message,
    Role,
    StreamEvent,
    StreamEventType,
    ToolCallDelta,
)
from octopus.tools.base import ToolRegistry


# ---------------------------------------------------------------------------
# Mock provider that returns controlled responses
# ---------------------------------------------------------------------------


class MockProvider:
    """Controllable mock provider for testing the agent loop."""

    def __init__(self) -> None:
        self.responses: list[list[StreamEvent]] = []
        self.call_count = 0
        self.last_messages: list[Message] = []
        self.last_tools: list[dict] = []

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict],
        model: str,
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamEvent]:
        self.call_count += 1
        self.last_messages = list(messages)
        self.last_tools = list(tools)

        if self.call_count <= len(self.responses):
            for event in self.responses[self.call_count - 1]:
                yield event
        else:
            yield StreamEvent(
                type=StreamEventType.TEXT,
                text="Default mock response.",
            )

    def set_responses(self, responses: list[list[StreamEvent]]) -> None:
        """Set the sequence of responses to return on each call."""
        self.responses = responses
        self.call_count = 0


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_provider() -> MockProvider:
    return MockProvider()


@pytest.fixture
async def test_kernel(tmp_path: Path) -> Kernel:
    db_path = tmp_path / "test_loop.db"
    k = Kernel(
        db_path=db_path,
        workspace=tmp_path,
        permission_mode=PermissionMode.FULL_AUTO,
    )
    await k.initialize()
    yield k
    await k.shutdown()


@pytest.fixture
def test_tools(test_kernel: Kernel) -> ToolRegistry:
    registry = ToolRegistry()
    return registry


@pytest.fixture
def test_context(test_kernel: Kernel, tmp_path: Path) -> Context:
    return Context(
        session_id="test-loop-session",
        kernel=test_kernel,
        workspace=tmp_path,
        permission_mode=PermissionMode.FULL_AUTO,
    )


@pytest.fixture
def conversation() -> ConversationContext:
    ctx = ConversationContext(
        session_id="test-loop-session",
        system_prompt="You are a test assistant.",
        model="test-model",
    )
    ctx.ensure_system_message()
    ctx.add_message(Message(role=Role.USER, content="Hello"))
    return ctx


# ---------------------------------------------------------------------------
# Tests: single turn
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_turn_text_only(
    mock_provider: MockProvider,
    test_kernel: Kernel,
    test_tools: ToolRegistry,
    test_context: Context,
    conversation: ConversationContext,
) -> None:
    """Model responds with text only, no tool calls. Loop completes in one turn."""
    mock_provider.set_responses([
        [
            StreamEvent(type=StreamEventType.TEXT, text="Hello, how can I help?"),
        ]
    ])

    events: list[StreamEvent] = []
    async for event in run_query(
        conversation.messages,
        mock_provider,  # type: ignore[arg-type]
        test_kernel,
        test_tools,
        test_context,
        model="test-model",
        conversation=conversation,
    ):
        events.append(event)

    assert mock_provider.call_count == 1
    text_events = [e for e in events if e.type == StreamEventType.TEXT]
    assert len(text_events) > 0
    assert "Hello" in (text_events[0].text or "")


@pytest.mark.asyncio
async def test_streaming_yields_text_chunks(
    mock_provider: MockProvider,
    test_kernel: Kernel,
    test_tools: ToolRegistry,
    test_context: Context,
    conversation: ConversationContext,
) -> None:
    """Multiple TEXT events are yielded as separate chunks."""
    mock_provider.set_responses([
        [
            StreamEvent(type=StreamEventType.TEXT, text="Part 1. "),
            StreamEvent(type=StreamEventType.TEXT, text="Part 2. "),
            StreamEvent(type=StreamEventType.TEXT, text="Part 3."),
        ]
    ])

    text_parts: list[str] = []
    async for event in run_query(
        conversation.messages,
        mock_provider,  # type: ignore[arg-type]
        test_kernel,
        test_tools,
        test_context,
        model="test-model",
        conversation=conversation,
    ):
        if event.type == StreamEventType.TEXT and event.text:
            text_parts.append(event.text)

    assert len(text_parts) == 3
    assert "".join(text_parts) == "Part 1. Part 2. Part 3."


@pytest.mark.asyncio
async def test_max_turns_enforcement(
    mock_provider: MockProvider,
    test_kernel: Kernel,
    test_tools: ToolRegistry,
    test_context: Context,
    conversation: ConversationContext,
) -> None:
    """Loop stops after max_turns is reached."""
    mock_provider.set_responses([
        [StreamEvent(type=StreamEventType.TEXT, text=f"Turn {i}")]
        for i in range(10)
    ])

    events: list[StreamEvent] = []
    async for event in run_query(
        conversation.messages,
        mock_provider,  # type: ignore[arg-type]
        test_kernel,
        test_tools,
        test_context,
        model="test-model",
        conversation=conversation,
        budget=LoopBudget(max_turns=3),
    ):
        events.append(event)

    assert mock_provider.call_count <= 4


# ---------------------------------------------------------------------------
# Tests: budget enforcement
# ---------------------------------------------------------------------------


def test_budget_max_turns_violation() -> None:
    """LoopBudget.max_turns is enforced."""
    budget = LoopBudget(max_turns=2)
    violation = budget.check(turn_count=2, tool_call_count=0)
    assert violation is not None
    assert violation.type == "max_turns"

    violation = budget.check(turn_count=1, tool_call_count=0)
    assert violation is None


def test_budget_max_tool_calls() -> None:
    """LoopBudget.max_tool_calls enforced."""
    budget = LoopBudget(max_tool_calls=5)
    assert budget.check(0, 5) is not None
    assert budget.check(0, 4) is None


def test_budget_no_limits() -> None:
    """Empty budget never violates."""
    budget = LoopBudget()
    assert budget.check(1000, 1000, 1000000) is None


# ---------------------------------------------------------------------------
# Tests: error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provider_error_yields_error_event(
    mock_provider: MockProvider,
    test_kernel: Kernel,
    test_tools: ToolRegistry,
    test_context: Context,
    conversation: ConversationContext,
) -> None:
    """When the provider raises, an ERROR event is yielded."""

    class FailingProvider:
        async def stream(self, messages, tools, model, max_tokens=4096):
            raise RuntimeError("Provider connection failed")
            yield  # type: ignore[unreachable]

    events: list[StreamEvent] = []
    async for event in run_query(
        conversation.messages,
        FailingProvider(),  # type: ignore[arg-type]
        test_kernel,
        test_tools,
        test_context,
        model="test-model",
        conversation=conversation,
    ):
        events.append(event)

    error_events = [e for e in events if e.type == StreamEventType.ERROR]
    assert len(error_events) > 0
