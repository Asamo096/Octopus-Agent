"""LiteLLM provider adapter — unified access to 100+ LLM providers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from octopus.loop.models import (
    Message,
    StreamEvent,
    StreamEventType,
    ToolCallDelta,
)


class LiteLLMProvider:
    """Unified LLM provider via litellm.

    Wraps litellm.acompletion with streaming support and converts
    the response chunks into Octopus StreamEvents.
    """

    def __init__(
        self, *, api_key: str | None = None, base_url: str | None = None
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        model: str,
        *,
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamEvent]:
        """Stream the model response via litellm."""
        import litellm

        # Convert messages to litellm format
        litellm_messages = [m.to_dict() for m in messages]

        # Build kwargs
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": litellm_messages,
            "stream": True,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
        if self._api_key:
            kwargs["api_key"] = self._api_key
        if self._base_url:
            kwargs["base_url"] = self._base_url

        # Accumulate tool calls across chunks
        tool_calls: dict[int, ToolCallDelta] = {}

        try:
            response = await litellm.acompletion(**kwargs)

            async for chunk in response:
                # Extract usage if present
                if hasattr(chunk, "usage") and chunk.usage:
                    yield StreamEvent(
                        type=StreamEventType.USAGE,
                        usage={
                            "prompt_tokens": chunk.usage.prompt_tokens or 0,
                            "completion_tokens": chunk.usage.completion_tokens or 0,
                            "total_tokens": chunk.usage.total_tokens or 0,
                        },
                    )

                if not chunk.choices:
                    continue

                choice = chunk.choices[0]
                delta = choice.delta

                # Text content
                if delta and delta.content:
                    yield StreamEvent(type=StreamEventType.TEXT, text=delta.content)

                # Tool calls
                if delta and delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_calls:
                            tool_calls[idx] = ToolCallDelta(
                                id=tc_delta.id or "",
                                name=tc_delta.function.name
                                if tc_delta.function and tc_delta.function.name
                                else "",
                                arguments="",
                            )
                        else:
                            # Update id/name if provided
                            if tc_delta.id:
                                tool_calls[idx].id = tc_delta.id
                            if tc_delta.function and tc_delta.function.name:
                                tool_calls[idx].name = tc_delta.function.name

                        # Accumulate arguments
                        if tc_delta.function and tc_delta.function.arguments:
                            tool_calls[idx].arguments += tc_delta.function.arguments

            # Yield completed tool calls
            for tc in tool_calls.values():
                yield StreamEvent(type=StreamEventType.TOOL_CALL, tool_call=tc)

            yield StreamEvent(type=StreamEventType.DONE)

        except Exception as e:
            yield StreamEvent(type=StreamEventType.ERROR, error=str(e))
            yield StreamEvent(type=StreamEventType.DONE)
