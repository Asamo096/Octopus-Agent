"""Data models for the agent loop — messages, tool calls, stream events."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

class Role(str, Enum):
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
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCallDelta]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to litellm/OpenAI-compatible dict."""
        d: Dict[str, Any] = {"role": self.role.value}
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

class StreamEventType(str, Enum):
    TEXT = "text"              # A chunk of assistant text
    TOOL_CALL = "tool_call"   # A complete tool call
    USAGE = "usage"           # Token usage update
    ERROR = "error"           # An error occurred
    DONE = "done"             # Stream finished


@dataclass
class StreamEvent:
    """An event yielded during streaming."""
    type: StreamEventType
    text: Optional[str] = None
    tool_call: Optional[ToolCallDelta] = None
    usage: Optional[Dict[str, int]] = None
    error: Optional[str] = None
