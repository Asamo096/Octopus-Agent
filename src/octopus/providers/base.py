"""Provider protocol — abstraction over LLM APIs."""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List, Protocol

from octopus.loop.models import Message, StreamEvent
from octopus.tools.base import Tool


class Provider(Protocol):
    """Protocol that all LLM providers must implement."""

    async def stream(
        self,
        messages: List[Message],
        tools: List[Dict[str, Any]],
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
