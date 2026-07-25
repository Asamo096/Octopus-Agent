"""Conversation compaction -- strategies for handling context overflow.

Implements a hybrid approach (matching OpenHarness):
1. Microcompact: clear old tool result content (free, instant)
2. Context collapse: truncate oversized text blocks (deterministic)
3. Session memory: LLM-generated summary of older messages (costs tokens)
4. Full LLM compaction: complete conversation summary (last resort)

Auto-compact triggers before each API call when token count exceeds threshold.
Reactive compact triggers on "prompt too long" errors.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from octopus.loop.context import ConversationContext
from octopus.loop.models import CompactBoundaryData, Message, Role

logger = logging.getLogger(__name__)

# Default thresholds
DEFAULT_AUTO_COMPACT_THRESHOLD = 80_000  # tokens
DEFAULT_MAX_INLINE_TOOL_RESULT = 2000  # characters
DEFAULT_CONTEXT_COLLAPSE_MAX = 5000  # characters per text block

# Tool types eligible for microcompact clearing
COMPACTABLE_TOOLS = {
    "read",
    "read_file",
    "write",
    "write_file",
    "edit",
    "edit_file",
    "shell",
    "glob",
    "grep",
    "web_search",
    "web_fetch",
}


class CompactionStrategy(StrEnum):
    """Available compaction strategies."""

    MICROCOMPACT = "microcompact"  # Clear old tool results
    TIME_MICROCOMPACT = "time_microcompact"  # Time-based tool result clearing
    CONTEXT_COLLAPSE = "context_collapse"  # Truncate large text blocks
    SESSION_MEMORY = "session_memory"  # LLM summary of old messages
    FULL_LLM = "full_llm"  # Full conversation summary
    REACTIVE_MICROCOMPACT = "reactive_microcompact"
    REACTIVE_COLLAPSE = "reactive_collapse"
    REACTIVE_LLM = "reactive_llm"


@dataclass
class MicrocompactConfig:
    """Configuration for time-based microcompact."""

    max_turns: int = 5  # Clear results older than N turns
    preserve_last_n: int = 2  # Always keep last N tool results per type
    cleared_marker: str = "[Previous tool result cleared]"


@dataclass
class CompactionResult:
    """Result of a compaction operation."""

    compacted: bool
    strategy: CompactionStrategy | None
    tokens_before: int
    tokens_after: int
    needs_llm_compaction: bool = False
    compacted_messages: list[Message] = field(default_factory=list)
    original_count: int = 0
    boundary: CompactBoundaryData | None = None


class CompactionEngine:
    """Handles conversation compaction with multiple strategies.

    Usage:
        engine = CompactionEngine()
        result = engine.auto_compact(context)
        if result.compacted:
            print(f"Reduced from {result.tokens_before} to {result.tokens_after}")
    """

    def __init__(
        self,
        *,
        auto_compact_threshold: int = DEFAULT_AUTO_COMPACT_THRESHOLD,
        max_inline_tool_result: int = DEFAULT_MAX_INLINE_TOOL_RESULT,
        context_collapse_max: int = DEFAULT_CONTEXT_COLLAPSE_MAX,
    ) -> None:
        self.auto_compact_threshold = auto_compact_threshold
        self.max_inline_tool_result = max_inline_tool_result
        self.context_collapse_max = context_collapse_max

    def auto_compact(self, context: ConversationContext) -> CompactionResult:
        """Automatically choose and apply the right compaction strategy.

        Strategy selection:
        - If overflow < 20%: microcompact
        - If overflow < 50%: microcompact + context collapse
        - If overflow >= 50%: microcompact + context collapse + session memory hint
        """
        tokens_before = context.estimate_tokens()

        if tokens_before <= self.auto_compact_threshold:
            return CompactionResult(
                compacted=False,
                strategy=None,
                tokens_before=tokens_before,
                tokens_after=tokens_before,
            )

        overflow_ratio = (
            tokens_before - self.auto_compact_threshold
        ) / self.auto_compact_threshold

        # Always start with time-based microcompact, fall back to basic
        removed = self.time_based_microcompact(context.messages)
        if removed == 0:
            removed = self.microcompact(context)

        tokens_after_mc = context.estimate_tokens()
        if tokens_after_mc <= self.auto_compact_threshold:
            logger.info(
                "Microcompact: %d -> %d tokens (removed %d tool results)",
                tokens_before,
                tokens_after_mc,
                removed,
            )
            result = CompactionResult(
                compacted=True,
                strategy=CompactionStrategy.TIME_MICROCOMPACT,
                tokens_before=tokens_before,
                tokens_after=tokens_after_mc,
            )
            result.boundary = self._build_boundary(result)
            return result

        # Still over threshold -- apply context collapse
        self.context_collapse(context)
        tokens_after_cc = context.estimate_tokens()

        if tokens_after_cc <= self.auto_compact_threshold:
            logger.info(
                "Microcompact + context collapse: %d -> %d tokens",
                tokens_before,
                tokens_after_cc,
            )
            result = CompactionResult(
                compacted=True,
                strategy=CompactionStrategy.CONTEXT_COLLAPSE,
                tokens_before=tokens_before,
                tokens_after=tokens_after_cc,
            )
            result.boundary = self._build_boundary(result)
            return result

        # Still over -- suggest session memory compaction
        if overflow_ratio >= 0.5:
            logger.warning(
                "Heavy overflow (%.0f%%). Session memory compaction recommended. "
                "Current: %d tokens, threshold: %d",
                overflow_ratio * 100,
                tokens_after_cc,
                self.auto_compact_threshold,
            )

        result = CompactionResult(
            compacted=True,
            strategy=CompactionStrategy.SESSION_MEMORY,
            tokens_before=tokens_before,
            tokens_after=tokens_after_cc,
            needs_llm_compaction=True,
        )
        result.boundary = self._build_boundary(result)
        return result

    def reactive_compact(
        self, context: ConversationContext, error: str
    ) -> CompactionResult:
        """Handle 'prompt too long' errors from the provider.

        Aggressively compacts the conversation to fit within limits.
        """
        tokens_before = context.estimate_tokens()

        # Microcompact first
        self.microcompact(context)

        # Then aggressive context collapse
        self.context_collapse(context, max_chars=self.context_collapse_max // 2)

        tokens_after = context.estimate_tokens()
        logger.info(
            "Reactive compact: %d -> %d tokens (triggered by: %s)",
            tokens_before,
            tokens_after,
            error[:100],
        )

        result = CompactionResult(
            compacted=True,
            strategy=CompactionStrategy.FULL_LLM,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            needs_llm_compaction=tokens_after > self.auto_compact_threshold,
        )
        result.boundary = self._build_boundary(result)
        return result

    async def reactive_compact_escalating(
        self,
        context: ConversationContext,
        error: Exception | str,
        provider: Any = None,
        attempt: int = 1,
        max_attempts: int = 3,
    ) -> CompactionResult:
        """Handle 'prompt too long' errors with escalating compaction strategies.

        Attempt 1: microcompact (clear old tool results)
        Attempt 2: context collapse (truncate large blocks) + microcompact
        Attempt 3: full LLM compaction (if provider available)

        Returns the CompactionResult. Raises the original error if it is not
        a prompt-too-long error.
        """
        error_msg = str(error).lower()
        is_prompt_too_long = any(
            pattern in error_msg
            for pattern in (
                "prompt is too long",
                "context_length_exceeded",
                "maximum context length",
                "tokens exceeds",
                "too long",
            )
        )

        if not is_prompt_too_long:
            raise error if isinstance(error, Exception) else RuntimeError(error)

        tokens_before = context.estimate_tokens()

        if attempt == 1:
            # Level 1: microcompact only
            removed = self.time_based_microcompact(
                context.messages,
                MicrocompactConfig(
                    max_turns=3,
                    preserve_last_n=1,
                    cleared_marker="[Previous tool result cleared]",
                ),
            )
            tokens_after = context.estimate_tokens()
            strategy = CompactionStrategy.REACTIVE_MICROCOMPACT
            logger.info(
                "Reactive compact attempt 1 (microcompact): %d -> %d tokens, "
                "cleared %d results",
                tokens_before,
                tokens_after,
                removed,
            )

        elif attempt == 2:
            # Level 2: microcompact + context collapse
            self.time_based_microcompact(
                context.messages,
                MicrocompactConfig(
                    max_turns=2,
                    preserve_last_n=0,
                ),
            )
            self.context_collapse(context, max_chars=2000)
            tokens_after = context.estimate_tokens()
            strategy = CompactionStrategy.REACTIVE_COLLAPSE
            logger.info(
                "Reactive compact attempt 2 (collapse): %d -> %d tokens",
                tokens_before,
                tokens_after,
            )

        else:
            # Level 3: full LLM compaction (if provider available)
            if provider is not None:
                return await self.session_memory_compact(context.messages, provider)

            # No provider -- fall back to aggressive non-LLM compaction
            self.time_based_microcompact(
                context.messages,
                MicrocompactConfig(max_turns=1, preserve_last_n=0),
            )
            self.context_collapse(context, max_chars=1000)
            tokens_after = context.estimate_tokens()
            strategy = CompactionStrategy.REACTIVE_LLM
            logger.info(
                "Reactive compact attempt 3 (aggressive): %d -> %d tokens",
                tokens_before,
                tokens_after,
            )

        result = CompactionResult(
            compacted=True,
            strategy=strategy,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            needs_llm_compaction=tokens_after > self.auto_compact_threshold,
        )
        result.boundary = self._build_boundary(result)
        return result

    def microcompact(self, context: ConversationContext) -> int:
        """Clear tool result content from messages older than the last 4 turns.

        This is free (no API call) and preserves the conversation structure
        while reclaiming significant space from verbose tool outputs.

        Returns the number of tool results cleared.
        """
        messages = context.messages
        if len(messages) <= 8:
            return 0

        # Find the cutoff: keep the last 8 messages intact
        cutoff = len(messages) - 8
        cleared = 0

        for i, msg in enumerate(messages):
            if i >= cutoff:
                break
            if msg.role == Role.TOOL and msg.content:
                # Replace content with a summary marker
                original_len = len(msg.content)
                if original_len > self.max_inline_tool_result:
                    msg.content = f"[Tool result truncated -- was {original_len} chars]"
                    cleared += 1

        return cleared

    def time_based_microcompact(
        self,
        messages: list[Message],
        config: MicrocompactConfig | None = None,
    ) -> int:
        """Clear tool results based on turn distance and per-tool-type tracking.

        Unlike the basic microcompact which just clears everything beyond a
        cutoff, this tracks per-tool-type occurrences and preserves the last N
        results of each tool type. This ensures the agent retains recent context
        for each tool category (e.g. the last 2 file reads, last 2 shell results).

        Returns the number of tool results cleared.
        """
        if config is None:
            config = MicrocompactConfig()

        if len(messages) <= config.max_turns * 2:
            return 0

        cleared_count = 0
        total_msgs = len(messages)

        # Track per-tool-type occurrence indices (assistant message index -> tool name)
        tool_occurrences: dict[str, list[int]] = {}

        for i, msg in enumerate(messages):
            if msg.role != Role.ASSISTANT or not msg.tool_calls:
                continue
            for tc in msg.tool_calls:
                tool_name = tc.name
                if tool_name not in COMPACTABLE_TOOLS:
                    continue
                if tool_name not in tool_occurrences:
                    tool_occurrences[tool_name] = []
                tool_occurrences[tool_name].append(i)

        # For each tool type, determine which occurrences to clear
        indices_to_clear: set[tuple[int, str]] = set()  # (assistant_idx, tool_call_id)
        for tool_name, indices in tool_occurrences.items():
            # Keep last N occurrences of this tool type
            if config.preserve_last_n > 0:
                to_check = indices[: -config.preserve_last_n]
            else:
                to_check = indices

            for idx in to_check:
                turn_distance = total_msgs - idx
                if turn_distance > config.max_turns:
                    msg = messages[idx]
                    if msg.tool_calls:
                        for tc in msg.tool_calls:
                            if tc.name == tool_name:
                                indices_to_clear.add((idx, tc.id))

        # Clear matching tool results
        for assistant_idx, tool_call_id in indices_to_clear:
            self._clear_tool_result(
                messages, assistant_idx, tool_call_id, config.cleared_marker
            )
            cleared_count += 1

        if cleared_count > 0:
            logger.info(
                "time_based_microcompact: cleared %d tool results", cleared_count
            )

        return cleared_count

    def _clear_tool_result(
        self,
        messages: list[Message],
        assistant_idx: int,
        tool_call_id: str,
        marker: str = "[Previous tool result cleared]",
    ) -> None:
        """Clear content of a tool result message while preserving structure.

        Finds the tool result message that corresponds to the given tool_call_id
        (which must appear after assistant_idx) and replaces its content.
        """
        for i in range(assistant_idx + 1, len(messages)):
            msg = messages[i]
            if msg.role == Role.TOOL and msg.tool_call_id == tool_call_id:
                msg.content = marker
                break

    def context_collapse(
        self,
        context: ConversationContext,
        *,
        max_chars: int | None = None,
    ) -> int:
        """Truncate oversized text blocks in assistant/user messages.

        Replaces the middle of long messages with a truncation marker.
        Returns the number of messages collapsed.
        """
        limit = max_chars or self.context_collapse_max
        collapsed = 0

        for msg in context.messages:
            if msg.role in (Role.ASSISTANT, Role.USER) and msg.content:
                if len(msg.content) > limit:
                    # Keep first 60% and last 30%, truncate middle
                    keep_start = int(limit * 0.6)
                    keep_end = int(limit * 0.3)
                    truncated = len(msg.content) - keep_start - keep_end
                    msg.content = (
                        msg.content[:keep_start]
                        + f"\n\n[... {truncated} chars truncated ...]\n\n"
                        + msg.content[-keep_end:]
                    )
                    collapsed += 1

        return collapsed

    async def session_memory_compact(
        self,
        messages: list[Message],
        provider: Any,
        *,
        summary_model: str = "claude-haiku-4-5-20251001",
        summary_max_tokens: int = 2000,
        extract_memories: bool = True,
    ) -> CompactionResult:
        """Compact with memory extraction.

        1. Extract facts worth remembering from the conversation
        2. Generate compaction summary that references extracted memories
        3. Replace messages with the summary

        Args:
            messages: Full conversation message history.
            provider: LLM provider for generating summaries.
            summary_model: Model to use for summarization.
            summary_max_tokens: Max tokens for the summary response.
            extract_memories: Whether to extract memories before summarizing.

        Returns:
            CompactionResult with the compacted message list.
        """
        tokens_before = self._estimate_tokens(messages)

        # Step 1: Extract memories (if enabled)
        extracted_facts: list[str] = []
        if extract_memories:
            try:
                extraction_prompt = self._build_extraction_prompt(messages)
                extraction_events = []
                async for event in provider.stream(
                    [Message(role=Role.USER, content=extraction_prompt)],
                    [],
                    summary_model,
                    max_tokens=1000,
                ):
                    if event.type.value == "text":
                        extraction_events.append(event.text or "")
                extraction_text = "".join(extraction_events)
                extracted_facts = self._parse_extracted_facts(extraction_text)
            except Exception as exc:
                logger.warning("Memory extraction failed: %s", exc)

        # Step 2: Generate summary with memory awareness
        summary_prompt = self._build_memory_aware_summary_prompt(
            messages, extracted_facts
        )
        summary_events = []
        try:
            async for event in provider.stream(
                [Message(role=Role.USER, content=summary_prompt)],
                [],
                summary_model,
                max_tokens=summary_max_tokens,
            ):
                if event.type.value == "text":
                    summary_events.append(event.text or "")
        except Exception as exc:
            logger.error("Summary generation failed: %s", exc)
            # Fall back to non-LLM compaction
            self.time_based_microcompact(
                messages, MicrocompactConfig(max_turns=2, preserve_last_n=0)
            )
            self.context_collapse(
                ConversationContext(session_id="temp", messages=messages)
            )
            tokens_after = self._estimate_tokens(messages)
            return CompactionResult(
                compacted=True,
                strategy=CompactionStrategy.FULL_LLM,
                tokens_before=tokens_before,
                tokens_after=tokens_after,
            )

        summary = "".join(summary_events)
        if extracted_facts:
            summary += "\n\nStored memories from this session:\n"
            for fact in extracted_facts:
                summary += f"- {fact}\n"

        # Build compacted messages
        compacted = [
            Message(
                role=Role.USER,
                content=f"Conversation summary:\n{summary}",
            ),
        ]

        tokens_after = self._estimate_tokens(compacted)
        result = CompactionResult(
            compacted=True,
            strategy=CompactionStrategy.SESSION_MEMORY,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            compacted_messages=compacted,
            original_count=len(messages),
        )
        result.boundary = self._build_boundary(
            result, extracted_memories=extracted_facts
        )
        return result

    def _build_extraction_prompt(self, messages: list[Message]) -> str:
        """Build prompt for fact extraction from conversation history."""
        conversation = _format_messages_for_summary(messages)
        return (
            "Extract important facts from this conversation that should be "
            "remembered for future sessions.\n\n"
            "Focus on:\n"
            "- User preferences and corrections\n"
            "- Project decisions and their rationale\n"
            "- Key technical facts discovered\n"
            "- Action items or TODOs\n"
            "- External references (URLs, file paths, config values)\n\n"
            "Format each fact as a single line. Do NOT include:\n"
            "- Temporary debugging info\n"
            "- Obvious facts derivable from code\n"
            '- Conversation mechanics ("user asked me to...")\n\n'
            f"Conversation:\n{conversation}\n\n"
            "Extracted facts (one per line):"
        )

    def _build_memory_aware_summary_prompt(
        self, messages: list[Message], extracted_facts: list[str]
    ) -> str:
        """Build summary prompt that is aware of extracted memories."""
        conversation = _format_messages_for_summary(messages)

        memory_section = ""
        if extracted_facts:
            memory_lines = "\n".join(f"- {fact}" for fact in extracted_facts)
            memory_section = (
                f"\nThe following facts have already been extracted and stored:\n"
                f"{memory_lines}\n"
                f"Do not repeat them in the summary; focus on contextual information.\n"
            )

        return (
            "Summarize the following conversation into a concise session memory. "
            "Preserve:\n"
            "1. Key decisions and their rationale\n"
            "2. Files modified and what was changed\n"
            "3. Current task state and next steps\n"
            "4. Important context for continuing the conversation\n"
            f"{memory_section}\n"
            "Format as structured markdown with sections for: "
            "Context, Work Done, Current State, Next Steps.\n\n"
            f"Conversation:\n{conversation}"
        )

    @staticmethod
    def _parse_extracted_facts(response: str) -> list[str]:
        """Parse extracted facts from LLM response."""
        facts = []
        for line in response.strip().split("\n"):
            line = line.strip()
            if line and not line.startswith("#") and len(line) > 10:
                # Strip list markers
                for prefix in ("- ", "* ", "1. ", "2. ", "3. ", "4. "):
                    if line.startswith(prefix):
                        line = line[len(prefix) :]
                        break
                facts.append(line)
        return facts[:20]  # Cap at 20 facts per compaction

    @staticmethod
    def _estimate_tokens(messages: list[Message]) -> int:
        """Estimate total token count for a message list."""
        total_chars = 0
        for msg in messages:
            if msg.content:
                total_chars += len(msg.content)
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    total_chars += len(tc.name) + len(tc.arguments)
        return total_chars // 4

    def apply_compaction(
        self,
        context: ConversationContext,
        result: CompactionResult,
    ) -> None:
        """Apply compaction result to context, inserting a boundary marker.

        After compaction, the context is replaced with:
        1. A compact boundary system message (metadata for session resume)
        2. The compacted messages (or the remaining tail of the original)

        This enables session resume from the compaction point.
        """
        if result.boundary is None:
            result.boundary = self._build_boundary(result)

        boundary_msg = Message(
            role=Role.SYSTEM,
            content=f"[Conversation compacted: {result.strategy.value if result.strategy else 'unknown'}]",
        )
        # Store boundary metadata as a dict on the message for serialization
        boundary_msg._compact_boundary = result.boundary  # type: ignore[attr-defined]

        if result.compacted_messages:
            # Full LLM compaction produced new messages
            context.messages = [boundary_msg] + result.compacted_messages
        else:
            # In-place compaction was already applied; just prepend the boundary
            context.messages.insert(0, boundary_msg)

    @staticmethod
    def _build_boundary(
        result: CompactionResult,
        extracted_memories: list[str] | None = None,
    ) -> CompactBoundaryData:
        """Build compact boundary data from a compaction result."""
        return CompactBoundaryData(
            strategy=result.strategy.value if result.strategy else "unknown",
            original_count=result.original_count,
            compacted_count=len(result.compacted_messages)
            if result.compacted_messages
            else 0,
            tokens_before=result.tokens_before,
            tokens_after=result.tokens_after,
            extracted_memories=extracted_memories or [],
        )


def _format_messages_for_summary(messages: list[Message]) -> str:
    """Format messages into a readable text for LLM summarization."""
    formatted: list[str] = []
    for msg in messages:
        if msg.role == Role.SYSTEM:
            formatted.append(f"[System]: {msg.content or ''}")
        elif msg.role == Role.USER:
            formatted.append(f"[User]: {msg.content or ''}")
        elif msg.role == Role.ASSISTANT:
            text = msg.content or ""
            if msg.tool_calls:
                tools = ", ".join(tc.name for tc in msg.tool_calls)
                text += f" [Used tools: {tools}]"
            formatted.append(f"[Assistant]: {text}")
        elif msg.role == Role.TOOL:
            formatted.append(f"[Tool Result]: {(msg.content or '')[:200]}")

    return "\n".join(formatted)


def session_memory_compact_prompt(messages: list[Message]) -> str:
    """Generate a prompt for LLM-based session memory compaction.

    This produces a structured request for the LLM to summarize older
    messages while preserving key context.
    """
    conversation_text = _format_messages_for_summary(messages)

    return (
        "Summarize the following conversation into a concise session memory. "
        "Preserve:\n"
        "1. Key decisions and their rationale\n"
        "2. Files modified and what was changed\n"
        "3. Current task state and next steps\n"
        "4. Important context for continuing the conversation\n\n"
        "Format as structured markdown with sections for: "
        "Context, Work Done, Current State, Next Steps.\n\n"
        f"Conversation:\n{conversation_text}"
    )
