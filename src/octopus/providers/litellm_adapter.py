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
        """Stream the model response via litellm.

        For providers with native function calling (openai, anthropic, etc.),
        sends tools as API parameters. For providers without (xiaomi_mimo, etc.),
        injects tool descriptions into the system prompt and expects XML output.
        """
        import litellm

        litellm.drop_params = True

        # Convert messages and handle tool injection for non-native providers
        litellm_messages = [m.to_dict() for m in messages]
        use_native = tools and _supports_native_tools(model)
        if tools and not use_native:
            litellm_messages = _inject_tools_xml(litellm_messages, tools)

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": litellm_messages,
            "stream": True,
            "max_tokens": max_tokens,
        }
        if use_native:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
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


# ---------------------------------------------------------------------------
# Helper: native tool support detection + XML injection for non-native providers
# ---------------------------------------------------------------------------


def _supports_native_tools(model: str) -> bool:
    """Check if the provider supports native function calling via API params."""
    native = {"openai", "anthropic", "deepseek", "groq", "together_ai",
              "fireworks_ai", "bedrock", "vertex_ai", "azure", "mistral"}
    prefix = model.split("/")[0] if "/" in model else ""
    return prefix in native


def _inject_tools_xml(
    messages: list[dict[str, Any]], tools: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Inject tool definitions into system prompt as XML format.

    For providers without native function calling, tools are described
    as text and the model outputs <tool_call> XML blocks.
    """
    lines = [
        "\n<system>",
        "You have tools. Use them by outputting XML in this format:",
        "",
        "<tool_call>",
        "<function=write_file>",
        "<parameter=path>/path/to/file</parameter>",
        "<parameter=content>file content here</parameter>",
        "</function>",
        "</tool_call>",
        "",
        "Available tools:",
    ]
    for t in tools:
        fn = t.get("function", t)
        name = fn.get("name", "")
        desc = fn.get("description", "")
        params = fn.get("parameters", {}).get("properties", {})
        required = fn.get("parameters", {}).get("required", [])
        lines.append(f"\n## {name}")
        lines.append(f"  {desc}")
        for pname, pinfo in params.items():
            req = " (required)" if pname in required else ""
            lines.append(f"  - {pname}: {pinfo.get('description', pinfo.get('type', 'str'))}{req}")
    lines.append("</system>")
    tool_text = "\n".join(lines)

    result = []
    injected = False
    for msg in messages:
        if msg.get("role") == "system" and not injected:
            result.append({**msg, "content": msg.get("content", "") + tool_text})
            injected = True
        else:
            result.append(msg)
    if not injected:
        result.insert(0, {"role": "system", "content": tool_text})
    return result
