"""IPC protocol — message types for GUI-CLI communication."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class MessageType(StrEnum):
    """Message types for the IPC protocol."""

    # Chat
    CHAT_SEND = "chat.send"
    CHAT_STREAM = "chat.stream"
    CHAT_DONE = "chat.done"

    # Tools
    TOOL_CALL = "tool.call"
    TOOL_RESULT = "tool.result"
    TOOL_APPROVE = "tool.approve"

    # Config
    CONFIG_GET = "config.get"
    CONFIG_SET = "config.set"

    # Sessions
    SESSION_LIST = "session.list"
    SESSION_CREATE = "session.create"
    SESSION_RESUME = "session.resume"

    # Audit
    AUDIT_QUERY = "audit.query"

    # Status
    STATUS = "status"
    ERROR = "error"


@dataclass
class IPCMessage:
    """A message in the IPC protocol."""

    id: str
    type: MessageType
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IPCMessage:
        return cls(
            id=data["id"],
            type=MessageType(data["type"]),
            payload=data.get("payload", {}),
        )
