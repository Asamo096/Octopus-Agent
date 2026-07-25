"""LiteLLM provider adapter — unified access to 100+ LLM providers."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from octopus.loop.models import (
    Message,
    StreamEvent,
    StreamEventType,
    ToolCallDelta,
)

logger = logging.getLogger(__name__)


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

        # Drop unsupported params automatically (e.g., tools for some providers)
        litellm.drop_params = True

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

        # Retry with exponential backoff for rate-limit errors
        max_retries = 10
        base_delay = 0.5
        max_delay = 32.0
        attempt = 0

        while True:
            attempt += 1
            try:
                response = await litellm.acompletion(**kwargs)
                break  # success, exit retry loop
            except Exception as exc:
                exc_str = str(exc).lower()
                # Check for 429 / 529 / rate-limit errors
                is_rate_limit = (
                    "429" in exc_str
                    or "529" in exc_str
                    or "rate" in exc_str
                    or "overloaded" in exc_str
                )
                if is_rate_limit and attempt < max_retries:
                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    logger.warning(
                        "Rate limited (attempt %d/%d), retrying in %.1fs",
                        attempt,
                        max_retries,
                        delay,
                    )
                    yield StreamEvent(
                        type=StreamEventType.STATUS,
                        text=f"[Rate limited, retrying in {delay:.1f}s (attempt {attempt}/{max_retries})]",
                    )
                    await asyncio.sleep(delay)
                    continue
                raise  # non-retryable or exhausted

        try:
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
