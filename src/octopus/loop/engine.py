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
from dataclasses import dataclass

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


# ---------------------------------------------------------------------------
# Budget enforcement (Pattern 7)
# ---------------------------------------------------------------------------


@dataclass
class BudgetViolation:
    """Represents a budget constraint violation."""

    type: str
    message: str
    current: float | int
    limit: float | int


@dataclass
class LoopBudget:
    """Budget constraints for agent loop execution.

    All fields are optional. None means no limit for that dimension.
    Checked before each turn in the agent loop.
    """

    max_turns: int | None = None
    max_tool_calls: int | None = None
    max_input_tokens: int | None = None

    def check(
        self,
        turn_count: int,
        tool_call_count: int,
        total_input_tokens: int = 0,
    ) -> BudgetViolation | None:
        """Check if any budget constraint is violated.

        Returns a BudgetViolation if a limit was exceeded, None otherwise.
        """
        if self.max_turns is not None and turn_count >= self.max_turns:
            return BudgetViolation(
                type="max_turns",
                message=f"Reached maximum number of turns ({self.max_turns})",
                current=turn_count,
                limit=self.max_turns,
            )

        if self.max_tool_calls is not None and tool_call_count >= self.max_tool_calls:
            return BudgetViolation(
                type="max_tool_calls",
                message=f"Reached maximum tool calls ({self.max_tool_calls})",
                current=tool_call_count,
                limit=self.max_tool_calls,
            )

        if self.max_input_tokens is not None and total_input_tokens >= self.max_input_tokens:
            return BudgetViolation(
                type="max_input_tokens",
                message=f"Reached maximum input tokens ({self.max_input_tokens})",
                current=total_input_tokens,
                limit=self.max_input_tokens,
            )

        return None


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
    budget: LoopBudget | None = None,
) -> AsyncIterator[StreamEvent]:
    """Run the agent loop.

    Yields StreamEvents as they arrive -- TEXT for assistant output,
    TOOL_CALL when a tool is invoked, USAGE for token counts,
    ERROR on failure, and DONE when finished.

    If a ConversationContext is provided, messages are synced to it and
    auto-compaction runs before each API call. If a CompactionEngine is
    provided without a ConversationContext, it is ignored.

    If a LoopBudget is provided, budget constraints are checked before
    each turn and execution stops gracefully on violation.
    """
    tools_def = registry.list_definitions()
    turns = 0
    tool_call_count = 0
    total_input_tokens = 0

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

        # Budget enforcement check before each turn
        if budget is not None:
            violation = budget.check(turns, tool_call_count, total_input_tokens)
            if violation is not None:
                logger.warning(
                    "Budget violation: %s (%s)",
                    violation.type,
                    violation.message,
                )
                yield StreamEvent(
                    type=StreamEventType.ERROR,
                    error=f"Budget exceeded: {violation.message}",
                )
                yield StreamEvent(type=StreamEventType.DONE)
                return

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

        # Sanitize messages: remove orphaned tool_use/tool_result blocks
        messages[:] = _sanitize_messages(messages)

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
                    if event.usage:
                        total_input_tokens += event.usage.get("prompt_tokens", 0)
                    yield event
                elif event.type == StreamEventType.ERROR:
                    yield event
                    yield StreamEvent(type=StreamEventType.DONE)
                    return
                elif event.type == StreamEventType.DONE:
                    break

            # Strip thinking blocks from output (some models leak internal reasoning)
            if collected_tool_calls:
                import re
                full_text = "".join(collected_text)
                cleaned = re.sub(r"<thinking>.*?</thinking>", "", full_text, flags=re.DOTALL).strip()
                if cleaned != full_text.strip():
                    collected_text.clear()
                    if cleaned:
                        collected_text.append(cleaned)

            # If no tool calls from provider, try parsing XML tool calls
            # (some providers/models output XML instead of function calling)
            if not collected_tool_calls:
                import re
                full_text = "".join(collected_text)
                # Strip thinking blocks
                full_text = _strip_model_artifacts(full_text)
                xml_calls = _parse_xml_tool_calls(full_text)
                if xml_calls:
                    collected_tool_calls = xml_calls
                    cleaned = _strip_xml_tool_calls(full_text)
                    collected_text.clear()
                    if cleaned:
                        collected_text.append(cleaned)
                else:
                    # Try parsing bash code blocks as shell tool calls
                    code_calls = _parse_code_block_calls(full_text)
                    if code_calls:
                        collected_tool_calls = code_calls
                        import re
                        # Remove code blocks (with or without language tag, with or without closing ```)
                        cleaned = re.sub(r"```(?:bash|sh|shell|zsh)?\n.*?(?:```|$)", "", full_text, flags=re.DOTALL)
                        # Also remove stray ``` markers
                        cleaned = re.sub(r"```", "", cleaned)
                        cleaned = cleaned.strip()
                        collected_text.clear()
                        if cleaned:
                            collected_text.append(cleaned)
                    else:
                        # If the entire response looks like a bare shell command, execute it
                        stripped = full_text.strip()
                        if _is_shell_command(stripped):
                            collected_tool_calls = [ToolCallDelta(
                                id="bare_cmd_0",
                                name="shell",
                                arguments=json.dumps({"command": stripped}),
                            )]
                            collected_text.clear()

            # Deduplicate tool calls - only execute unique commands
            if collected_tool_calls:
                seen = set()
                unique_calls = []
                for tc in collected_tool_calls:
                    key = (tc.name, tc.arguments)
                    if key not in seen:
                        seen.add(key)
                        unique_calls.append(tc)
                collected_tool_calls = unique_calls
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
        tool_call_count += len(collected_tool_calls)

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

    # Map common tool name variations to registered names
    _TOOL_NAME_MAP = {
        "execute_shell": "shell",
        "execute_command": "shell",
        "run_command": "shell",
        "bash": "shell",
        "execute_block": "shell",
        "read_file": "read",
        "file_read": "read",
        "write_file": "write",
        "file_write": "write",
        "edit_file": "edit",
        "file_edit": "edit",
        "search_files": "grep",
        "find_files": "glob",
    }
    tool_name = _TOOL_NAME_MAP.get(tc.name, tc.name)

    tool = registry.get(tool_name)
    if tool is None:
        return ToolResult(
            success=False, output=None, error=f"Tool not found: {tc.name}"
        )

    # Create ToolCall for the kernel
    tool_call = ToolCall(tool_name=tool_name, arguments=args, call_id=tc.id)

    # Execute through the kernel's harness pipeline
    return await kernel.execute_tool(tool_call, ctx)




def _strip_model_artifacts(text: str) -> str:
    """Strip model-specific artifacts from output text."""
    import re
    # Strip thinking blocks
    text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL)
    # Strip <|python_tag|> and similar markers
    text = re.sub(r"<\|.*?\|>", "", text)
    # Strip <think>...</think> blocks
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # Strip stray code block markers
    text = re.sub(r"```(?:\w+)?", "", text)
    # Clean up extra whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _is_shell_command(text: str) -> bool:
    """Check if text looks like a bare shell command."""
    if not text or len(text) > 500:
        return False
    # Single line or simple chained commands
    lines = text.strip().split("\n")
    if len(lines) > 3:
        return False
    # Common shell command prefixes
    prefixes = [
        "echo ", "cat ", "ls ", "rm ", "mv ", "cp ", "mkdir ", "touch ",
        "chmod ", "chown ", "grep ", "find ", "sed ", "awk ", "curl ",
        "wget ", "pip ", "npm ", "git ", "python ", "python3 ",
        "cd ", "pwd", "whoami", "date", "which ", "apt ", "brew ",
    ]
    first_line = lines[0].strip()
    return any(first_line.startswith(p) for p in prefixes)


def _parse_xml_tool_calls(text: str) -> list[ToolCallDelta]:
    """Parse XML-formatted tool calls from model output."""
    import re

    calls: list[ToolCallDelta] = []
    call_id = 0

    # Format 1: <tool_call>...</tool_call>
    pattern1 = r"<tool_call>(.*?)</tool_call>"
    for block in re.findall(pattern1, text, re.DOTALL):
        name_match = re.search(r"<tool_name>\s*(.*?)\s*</tool_name>", block, re.DOTALL)
        if not name_match:
            continue
        tool_name = name_match.group(1).strip()
        args_match = re.search(r"<(?:arguments|tool_input)>\s*(.*?)\s*</(?:arguments|tool_input)>", block, re.DOTALL)
        args_str = args_match.group(1).strip() if args_match else "{}"
        try:
            json.loads(args_str)
        except json.JSONDecodeError:
            args_str = "{}"
        calls.append(ToolCallDelta(id=f"xml_call_{call_id}", name=tool_name, arguments=args_str))
        call_id += 1

    # Format 2: <function=name>...</function>
    pattern2 = r"<function=(.*?)>(.*?)</function>"
    for func_name, body in re.findall(pattern2, text, re.DOTALL):
        tool_name = func_name.strip()
        params: dict[str, str] = {}
        for pm in re.finditer(r"<parameter=(\w+)>(.*?)</parameter>", body, re.DOTALL):
            params[pm.group(1)] = pm.group(2).strip()
        if "command" in params:
            args_str = json.dumps({"command": params["command"]})
        elif "cmd" in params:
            args_str = json.dumps({"command": params["cmd"]})
        else:
            args_str = json.dumps(params)
        calls.append(ToolCallDelta(id=f"xml_call_{call_id}", name=tool_name, arguments=args_str))
        call_id += 1

    return calls


def _strip_xml_tool_calls(text: str) -> str:
    """Remove all XML tool call formats from text."""
    import re
    text = re.sub(r"<tool_call>.*?</tool_call>", "", text, flags=re.DOTALL)
    text = re.sub(r"<function=.*?>.*?</function>", "", text, flags=re.DOTALL)
    return text.strip()


def _sanitize_messages(messages: list[Message]) -> list[Message]:
    """Remove orphaned tool_use / tool_result blocks and empty messages.

    - assistant tool_use without matching tool_result  ->  remove that tool_use
    - tool_result without matching tool_use             ->  drop the message
    - empty messages                                    ->  drop
    """
    # Collect all tool_call_ids from assistant messages
    tool_call_ids: set[str] = set()
    for msg in messages:
        if msg.role == Role.ASSISTANT and msg.tool_calls:
            for tc in msg.tool_calls:
                if tc.id:
                    tool_call_ids.add(tc.id)

    # Collect all tool_result ids
    tool_result_ids: set[str] = set()
    for msg in messages:
        if msg.role == Role.TOOL and msg.tool_call_id:
            tool_result_ids.add(msg.tool_call_id)

    sanitized: list[Message] = []
    for msg in messages:
        # Drop orphaned tool_result messages
        if msg.role == Role.TOOL and msg.tool_call_id not in tool_call_ids:
            continue

        # Strip orphaned tool_calls from assistant messages
        if msg.role == Role.ASSISTANT and msg.tool_calls:
            kept = [tc for tc in msg.tool_calls if tc.id in tool_result_ids]
            if kept:
                msg.tool_calls = kept
            else:
                msg.tool_calls = None

        # Drop empty messages
        if not msg.content and not msg.tool_calls:
            continue

        sanitized.append(msg)

    return sanitized


def _parse_code_block_calls(text: str) -> list[ToolCallDelta]:
    """Parse bash/shell code blocks as shell tool calls.

    Handles format:
        ```bash
        touch test.txt
        ```
        ```sh
        ls -la
        ```
        ```
        echo hello
        ```
    """
    import re

    # Match code blocks with bash/sh/shell language tags or no tag
    # Also handle blocks without closing ```
    pattern = r"```(?:bash|sh|shell|zsh)?\n(.*?)(?:```|$)"
    matches = re.findall(pattern, text, re.DOTALL)

    calls: list[ToolCallDelta] = []
    for i, block in enumerate(matches):
        command = block.strip()
        if not command:
            continue

        # Skip if it looks like Python, JS, etc. (not a shell command)
        if any(command.startswith(lang) for lang in ["python", "py", "import ", "from ", "def ", "class "]):
            continue

        calls.append(ToolCallDelta(
            id=f"code_block_{i}",
            name="shell",
            arguments=json.dumps({"command": command}),
        ))

    return calls
