"""Agent loop — the core think-act-observe cycle.

The loop:
1. Auto-compact check before each API call
2. Streams the model response via the provider
3. If the model returns tool calls → execute them through the kernel
4. Append results to messages and loop back
5. If no tool calls → done, yield final text
6. Max turns enforcement
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from octopus.core.kernel import Context, Kernel, ToolCall, ToolResult
from octopus.loop.compaction import CompactionEngine
from octopus.loop.context import ConversationContext
from octopus.loop.models import (
    Message,
    Role,
    StreamEvent,
    StreamEventType,
    ToolCallDelta,
)
from octopus.providers.base import Provider
from octopus.tools.base import ToolRegistry

logger = logging.getLogger(__name__)

# Default max turns before forcing stop
DEFAULT_MAX_TURNS = 50


async def run_query(
    messages: list[Message],
    provider: Provider,
    kernel: Kernel,
    registry: ToolRegistry,
    ctx: Context,
    *,
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 4096,
    max_turns: int = DEFAULT_MAX_TURNS,
    conversation: ConversationContext | None = None,
    compaction: CompactionEngine | None = None,
) -> AsyncIterator[StreamEvent]:
    """Run the agent loop.

    Yields StreamEvents as they arrive — TEXT for assistant output,
    TOOL_CALL when a tool is invoked, USAGE for token counts,
    ERROR on failure, and DONE when finished.

    If a ConversationContext is provided, messages are synced to it and
    auto-compaction runs before each API call. If a CompactionEngine is
    provided without a ConversationContext, it is ignored.
    """
    tools_def = registry.list_definitions()
    turns = 0

    # Sync messages into conversation context if provided
    if conversation is not None:
        if not conversation.messages:
            conversation.messages = messages
        else:
            # Merge: conversation owns the history, messages is the working copy
            messages = conversation.messages

    while turns < max_turns:
        turns += 1
        logger.debug("Turn %d/%d", turns, max_turns)

        # Auto-compact before API call if conversation context is available
        if conversation is not None and compaction is not None:
            result = compaction.auto_compact(conversation)
            if result.compacted:
                logger.info(
                    "Auto-compact: %s (%d -> %d tokens)",
                    result.strategy,
                    result.tokens_before,
                    result.tokens_after,
                )
                yield StreamEvent(
                    type=StreamEventType.STATUS,
                    text=f"[Compacted: {result.tokens_before} → {result.tokens_after} tokens via {result.strategy}]",
                )

        # Stream the model response
        collected_text: list[str] = []
        collected_tool_calls: list[ToolCallDelta] = []

        try:
            async for event in provider.stream(
                messages, tools_def, model, max_tokens=max_tokens
            ):
                if event.type == StreamEventType.TEXT:
                    collected_text.append(event.text or "")
                    yield event
                elif event.type == StreamEventType.TOOL_CALL and event.tool_call:
                    collected_tool_calls.append(event.tool_call)
                elif event.type == StreamEventType.USAGE:
                    yield event
                elif event.type == StreamEventType.ERROR:
                    yield event
                    yield StreamEvent(type=StreamEventType.DONE)
                    return
                elif event.type == StreamEventType.DONE:
                    break

            # If no tool calls from provider, try parsing XML tool calls
            # (some providers/models output XML instead of function calling)
            if not collected_tool_calls:
                full_text = "".join(collected_text)
                xml_calls = _parse_xml_tool_calls(full_text)
                if xml_calls:
                    collected_tool_calls = xml_calls
                    # Remove XML from displayed text
                    import re
                    cleaned = re.sub(r"<tool_call>.*?</tool_call>", "", full_text, flags=re.DOTALL).strip()
                    collected_text.clear()
                    collected_text.append(cleaned)
        except Exception as exc:
            error_msg = str(exc)
            # Reactive compaction on "prompt too long" errors
            if (
                "too long" in error_msg.lower()
                or "context_length_exceeded" in error_msg.lower()
                or "prompt is too long" in error_msg.lower()
            ):
                if conversation is not None and compaction is not None:
                    rc = compaction.reactive_compact(conversation, error_msg)
                    logger.info(
                        "Reactive compact applied: %d -> %d tokens",
                        rc.tokens_before, rc.tokens_after,
                    )
                    yield StreamEvent(
                        type=StreamEventType.STATUS,
                        text=f"[Reactive compact: {rc.tokens_before} → {rc.tokens_after} tokens]",
                    )
                    # Retry the API call
                    continue
            # Not a prompt-too-long error, or no compaction available
            yield StreamEvent(type=StreamEventType.ERROR, error=error_msg)
            yield StreamEvent(type=StreamEventType.DONE)
            return

        # No tool calls → assistant is done
        if not collected_tool_calls:
            # Append assistant message to history
            assistant_text = "".join(collected_text)
            messages.append(
                Message(role=Role.ASSISTANT, content=assistant_text or None)
            )
            yield StreamEvent(type=StreamEventType.DONE)
            return

        # Build assistant message with tool calls
        assistant_msg = Message(
            role=Role.ASSISTANT,
            content="".join(collected_text) or None,
            tool_calls=collected_tool_calls,
        )
        messages.append(assistant_msg)

        # Execute tool calls (parallel)
        tool_tasks = [
            _execute_tool(kernel, registry, tc, ctx) for tc in collected_tool_calls
        ]
        tool_results = await asyncio.gather(*tool_tasks, return_exceptions=True)

        # Process results and yield events
        for tc, raw_result in zip(collected_tool_calls, tool_results, strict=True):
            if isinstance(raw_result, BaseException):
                tool_result = ToolResult(
                    success=False, output=None, error=str(raw_result)
                )
            else:
                tool_result = raw_result

            # Yield the tool call event
            yield StreamEvent(type=StreamEventType.TOOL_CALL, tool_call=tc)

            # Append tool result message
            messages.append(
                Message(
                    role=Role.TOOL,
                    content=json.dumps(
                        {
                            "output": tool_result.output,
                            "error": tool_result.error,
                            "success": tool_result.success,
                        }
                    ),
                    tool_call_id=tc.id,
                    name=tc.name,
                )
            )

    # Max turns exceeded
    logger.warning("Max turns (%d) exceeded", max_turns)
    yield StreamEvent(
        type=StreamEventType.ERROR,
        error=f"Max turns ({max_turns}) exceeded",
    )
    yield StreamEvent(type=StreamEventType.DONE)


async def _execute_tool(
    kernel: Kernel,
    registry: ToolRegistry,
    tc: ToolCallDelta,
    ctx: Context,
) -> ToolResult:
    """Execute a single tool call through the kernel."""
    # Parse arguments
    try:
        args = json.loads(tc.arguments) if tc.arguments else {}
    except json.JSONDecodeError:
        return ToolResult(
            success=False, output=None, error=f"Invalid JSON arguments: {tc.arguments}"
        )

    tool = registry.get(tc.name)
    if tool is None:
        return ToolResult(
            success=False, output=None, error=f"Tool not found: {tc.name}"
        )

    # Create ToolCall for the kernel
    tool_call = ToolCall(tool_name=tc.name, arguments=args, call_id=tc.id)

    # Execute through the kernel's harness pipeline
    return await kernel.execute_tool(tool_call, ctx)


def _parse_xml_tool_calls(text: str) -> list[ToolCallDelta]:
    """Parse XML-formatted tool calls from model output.

    Handles format:
        <tool_call>
        <tool_name>name</tool_name>
        <arguments>{"key": "value"}</arguments>
        </tool_call>
    """
    import re

    pattern = r"<tool_call>\s*(.*?)\s*</tool_call>"
    matches = re.findall(pattern, text, re.DOTALL)

    calls: list[ToolCallDelta] = []
    for i, block in enumerate(matches):
        # Extract tool name
        name_match = re.search(r"<tool_name>\s*(.*?)\s*</tool_name>", block, re.DOTALL)
        if not name_match:
            continue
        tool_name = name_match.group(1).strip()

        # Extract arguments (JSON string)
        args_match = re.search(r"<arguments>\s*(.*?)\s*</arguments>", block, re.DOTALL)
        args_str = args_match.group(1).strip() if args_match else "{}"

        # Validate JSON
        try:
            json.loads(args_str)
        except json.JSONDecodeError:
            args_str = "{}"

        calls.append(ToolCallDelta(
            id=f"xml_call_{i}",
            name=tool_name,
            arguments=args_str,
        ))

    return calls
