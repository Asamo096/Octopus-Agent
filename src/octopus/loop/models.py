"""Data models for the agent loop — messages, tool calls, stream events."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class ToolCallDelta:
    """A tool call as it arrives during streaming."""

    id: str
    name: str
    arguments: str  # JSON string, accumulated across chunks


@dataclass
class Message:
    """A single conversation message."""

    role: Role
    content: str | None = None
    tool_calls: list[ToolCallDelta] | None = None
    tool_call_id: str | None = None
    name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to litellm/OpenAI-compatible dict."""
        d: dict[str, Any] = {"role": self.role.value}
        if self.content is not None:
            d["content"] = self.content
        if self.tool_calls:
            d["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.arguments},
                }
                for tc in self.tool_calls
            ]
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        if self.name:
            d["name"] = self.name
        return d


# ---------------------------------------------------------------------------
# Stream events
# ---------------------------------------------------------------------------


class StreamEventType(StrEnum):
    TEXT = "text"  # A chunk of assistant text
    TOOL_CALL = "tool_call"  # A complete tool call
    USAGE = "usage"  # Token usage update
    ERROR = "error"  # An error occurred
    DONE = "done"  # Stream finished
    STATUS = "status"  # Status message (compaction, etc.)
    ACTIVITY = "activity"  # Tool activity description for spinner


@dataclass
class StreamEvent:
    """An event yielded during streaming."""

    type: StreamEventType
    text: str | None = None
    tool_call: ToolCallDelta | None = None
    usage: dict[str, int] | None = None
    error: str | None = None
    tool_data: dict[str, object] | None = None  # Extra tool result metadata for UI rendering


# ---------------------------------------------------------------------------
# Compact boundary data
# ---------------------------------------------------------------------------


@dataclass
class CompactBoundaryData:
    """Metadata for a compaction boundary message.

    After compaction, a boundary message is inserted into the conversation.
    Messages after the boundary are the active context; messages before
    the boundary have been summarized and can be released.
    This enables session resume from the compaction point.
    """

    strategy: str
    original_count: int
    compacted_count: int
    tokens_before: int
    tokens_after: int
    extracted_memories: list[str] | None = None
