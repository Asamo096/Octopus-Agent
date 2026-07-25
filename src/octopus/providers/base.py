"""Provider protocol — abstraction over LLM APIs."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

from octopus.loop.models import Message, StreamEvent


class Provider(Protocol):
    """Protocol that all LLM providers must implement."""

    def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        model: str,
        *,
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamEvent]:
        """Stream the model response as a sequence of StreamEvents.

        Args:
            messages: Conversation history.
            tools: Tool definitions in OpenAI function-calling format.
            model: Model identifier.
            max_tokens: Maximum tokens in the response.

        Yields:
            StreamEvent objects — TEXT, TOOL_CALL, USAGE, ERROR, or DONE.
        """
        ...
