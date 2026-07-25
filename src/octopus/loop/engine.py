"""Agent loop — the core think-act-observe cycle.

The loop:
1. Streams the model response via the provider
2. If the model returns tool calls → execute them through the kernel
3. Append results to messages and loop back
4. If no tool calls → done, yield final text
5. Max turns enforcement
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from octopus.core.kernel import Context, Kernel, ToolCall, ToolResult
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
    messages: List[Message],
    provider: Provider,
    kernel: Kernel,
    registry: ToolRegistry,
    ctx: Context,
    *,
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 4096,
    max_turns: int = DEFAULT_MAX_TURNS,
) -> AsyncIterator[StreamEvent]:
    """Run the agent loop.

    Yields StreamEvents as they arrive — TEXT for assistant output,
    TOOL_CALL when a tool is invoked, USAGE for token counts,
    ERROR on failure, and DONE when finished.
    """
    tools_def = registry.list_definitions()
    turns = 0

    while turns < max_turns:
        turns += 1
        logger.debug("Turn %d/%d", turns, max_turns)

        # Stream the model response
        collected_text: list[str] = []
        collected_tool_calls: list[ToolCallDelta] = []
        usage: Optional[Dict[str, int]] = None

        async for event in provider.stream(messages, tools_def, model, max_tokens=max_tokens):
            if event.type == StreamEventType.TEXT:
                collected_text.append(event.text or "")
                yield event
            elif event.type == StreamEventType.TOOL_CALL and event.tool_call:
                collected_tool_calls.append(event.tool_call)
            elif event.type == StreamEventType.USAGE:
                usage = event.usage
                yield event
            elif event.type == StreamEventType.ERROR:
                yield event
                yield StreamEvent(type=StreamEventType.DONE)
                return
            elif event.type == StreamEventType.DONE:
                break

        # No tool calls → assistant is done
        if not collected_tool_calls:
            # Append assistant message to history
            assistant_text = "".join(collected_text)
            messages.append(Message(role=Role.ASSISTANT, content=assistant_text or None))
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
            _execute_tool(kernel, registry, tc, ctx)
            for tc in collected_tool_calls
        ]
        tool_results = await asyncio.gather(*tool_tasks, return_exceptions=True)

        # Process results and yield events
        for tc, result in zip(collected_tool_calls, tool_results):
            if isinstance(result, Exception):
                result = ToolResult(success=False, output=None, error=str(result))

            # Yield the tool call event
            yield StreamEvent(type=StreamEventType.TOOL_CALL, tool_call=tc)

            # Append tool result message
            messages.append(Message(
                role=Role.TOOL,
                content=json.dumps({"output": result.output, "error": result.error, "success": result.success}),
                tool_call_id=tc.id,
                name=tc.name,
            ))

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
        return ToolResult(success=False, output=None, error=f"Invalid JSON arguments: {tc.arguments}")

    tool = registry.get(tc.name)
    if tool is None:
        return ToolResult(success=False, output=None, error=f"Tool not found: {tc.name}")

    # Create ToolCall for the kernel
    tool_call = ToolCall(tool_name=tc.name, arguments=args, call_id=tc.id)

    # Execute through the kernel's harness pipeline
    return await kernel.execute_tool(tool_call, ctx)
