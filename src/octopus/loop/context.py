"""Conversation context — message history management with persistence.

ConversationContext owns the full message history for a session, handles
serialization to/from SQLite, and provides token estimation for compaction
decisions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from octopus.loop.models import Message, Role, ToolCallDelta

logger = logging.getLogger(__name__)

# Rough heuristic: ~4 characters per token (English text)
CHARS_PER_TOKEN = 4


@dataclass
class ConversationContext:
    """Manages conversation message history with persistence.

    Attributes:
        session_id: Unique session identifier.
        system_prompt: The system prompt for this conversation.
        model: Model identifier to use.
        max_tokens: Max tokens per response.
        messages: Full conversation history.
    """

    session_id: str
    system_prompt: str = ""
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4096
    messages: list[Message] = field(default_factory=list)

    # ---- message management -------------------------------------------------

    def add_message(self, message: Message) -> None:
        """Append a message to the conversation history."""
        self.messages.append(message)

    def get_messages(self) -> list[Message]:
        """Return all messages (shallow copy)."""
        return list(self.messages)

    def clear(self) -> None:
        """Clear all messages."""
        self.messages.clear()

    def set_system_prompt(self, prompt: str) -> None:
        """Set or replace the system prompt."""
        self.system_prompt = prompt
        # Update the first message if it's a system message
        if self.messages and self.messages[0].role == Role.SYSTEM:
            self.messages[0].content = prompt
        else:
            # Insert system message at the beginning
            self.messages.insert(0, Message(role=Role.SYSTEM, content=prompt))

    def ensure_system_message(self) -> None:
        """Ensure the conversation starts with a system message."""
        if not self.messages or self.messages[0].role != Role.SYSTEM:
            self.messages.insert(
                0, Message(role=Role.SYSTEM, content=self.system_prompt)
            )

    # ---- token estimation ---------------------------------------------------

    def estimate_tokens(self) -> int:
        """Estimate total token count across all messages.

        Uses a rough heuristic (~4 chars per token). This is intentionally
        simple — accurate counting requires a tokenizer which adds a dependency.
        """
        total_chars = 0
        for msg in self.messages:
            if msg.content:
                total_chars += len(msg.content)
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    total_chars += len(tc.name) + len(tc.arguments)
        return total_chars // CHARS_PER_TOKEN

    # ---- persistence --------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize the context to a JSON-serializable dict."""
        return {
            "session_id": self.session_id,
            "system_prompt": self.system_prompt,
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [msg.to_dict() for msg in self.messages],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConversationContext:
        """Deserialize a context from a dict."""
        ctx = cls(
            session_id=data["session_id"],
            system_prompt=data.get("system_prompt", ""),
            model=data.get("model", "claude-sonnet-4-20250514"),
            max_tokens=data.get("max_tokens", 4096),
        )
        for msg_data in data.get("messages", []):
            ctx.messages.append(_message_from_dict(msg_data))
        return ctx

    async def save(self, state_manager: Any) -> None:
        """Persist the conversation to SQLite via StateManager.

        Stores messages as JSON in the session's `context` field.
        """
        await state_manager.update_session(
            self.session_id,
            context={
                "system_prompt": self.system_prompt,
                "model": self.model,
                "max_tokens": self.max_tokens,
                "messages": [msg.to_dict() for msg in self.messages],
            },
        )
        logger.debug(
            "Saved context for session %s (%d messages)",
            self.session_id,
            len(self.messages),
        )

    @classmethod
    async def load(
        cls, session_id: str, state_manager: Any
    ) -> ConversationContext | None:
        """Load a conversation context from SQLite.

        Returns None if the session doesn't exist or has no saved context.
        """
        session = await state_manager.get_session(session_id)
        if session is None:
            return None

        context_data = session.context
        if not context_data or "messages" not in context_data:
            # Session exists but has no saved messages — return empty context
            return cls(session_id=session_id)

        return cls.from_dict({"session_id": session_id, **context_data})

    # ---- sanitization -------------------------------------------------------

    def sanitize(self) -> None:
        """Normalize message history after loading from persistence.

        - Drops empty assistant messages
        - Trims orphan tool_use blocks (tool_use without matching tool result)
        - Ensures conversation starts with a system message
        """
        if not self.messages:
            return

        sanitized: list[Message] = []
        pending_tool_ids: set[str] = set()

        for msg in self.messages:
            # Track tool_call IDs from assistant messages
            if msg.role == Role.ASSISTANT and msg.tool_calls:
                for tc in msg.tool_calls:
                    pending_tool_ids.add(tc.id)
                # Keep assistant messages with tool calls even if content is empty
                sanitized.append(msg)
            elif msg.role == Role.TOOL:
                # Only keep tool results that match a pending tool_call
                if msg.tool_call_id and msg.tool_call_id in pending_tool_ids:
                    pending_tool_ids.discard(msg.tool_call_id)
                    sanitized.append(msg)
                # Drop orphan tool results
            elif msg.role == Role.ASSISTANT and not msg.content and not msg.tool_calls:
                # Drop empty assistant messages (no text, no tool calls)
                continue
            else:
                # User or system messages — keep as-is
                sanitized.append(msg)

        # Drop assistant messages whose tool_calls have no matching results
        final: list[Message] = []
        for msg in sanitized:
            if msg.role == Role.ASSISTANT and msg.tool_calls:
                # Check if all tool calls have results
                has_results = all(
                    tc.id not in pending_tool_ids for tc in msg.tool_calls
                )
                if has_results or not pending_tool_ids:
                    final.append(msg)
                else:
                    # Keep the text part but drop orphan tool calls
                    if msg.content:
                        final.append(
                            Message(
                                role=Role.ASSISTANT,
                                content=msg.content,
                            )
                        )
            else:
                final.append(msg)

        self.messages = final

        # Ensure system message at start
        self.ensure_system_message()


def _message_from_dict(data: dict[str, Any]) -> Message:
    """Convert a message dict back to a Message object."""
    role = Role(data["role"])
    tool_calls = None
    if data.get("tool_calls"):
        tool_calls = [
            ToolCallDelta(
                id=tc["id"],
                name=tc["function"]["name"],
                arguments=tc["function"]["arguments"],
            )
            for tc in data["tool_calls"]
        ]
    return Message(
        role=role,
        content=data.get("content"),
        tool_calls=tool_calls,
        tool_call_id=data.get("tool_call_id"),
        name=data.get("name"),
    )
