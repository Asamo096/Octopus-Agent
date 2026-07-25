"""Conversation compaction — strategies for handling context overflow.

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
from dataclasses import dataclass
from enum import StrEnum

from octopus.loop.context import ConversationContext
from octopus.loop.models import Message, Role

logger = logging.getLogger(__name__)

# Default thresholds
DEFAULT_AUTO_COMPACT_THRESHOLD = 80_000  # tokens
DEFAULT_MAX_INLINE_TOOL_RESULT = 2000  # characters
DEFAULT_CONTEXT_COLLAPSE_MAX = 5000  # characters per text block


class CompactionStrategy(StrEnum):
    """Available compaction strategies."""

    MICROCOMPACT = "microcompact"  # Clear old tool results
    CONTEXT_COLLAPSE = "context_collapse"  # Truncate large text blocks
    SESSION_MEMORY = "session_memory"  # LLM summary of old messages
    FULL_LLM = "full_llm"  # Full conversation summary


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

        # Always start with microcompact
        removed = self.microcompact(context)

        tokens_after_mc = context.estimate_tokens()
        if tokens_after_mc <= self.auto_compact_threshold:
            logger.info(
                "Microcompact: %d -> %d tokens (removed %d tool results)",
                tokens_before,
                tokens_after_mc,
                removed,
            )
            return CompactionResult(
                compacted=True,
                strategy=CompactionStrategy.MICROCOMPACT,
                tokens_before=tokens_before,
                tokens_after=tokens_after_mc,
            )

        # Still over threshold — apply context collapse
        self.context_collapse(context)
        tokens_after_cc = context.estimate_tokens()

        if tokens_after_cc <= self.auto_compact_threshold:
            logger.info(
                "Microcompact + context collapse: %d -> %d tokens",
                tokens_before,
                tokens_after_cc,
            )
            return CompactionResult(
                compacted=True,
                strategy=CompactionStrategy.CONTEXT_COLLAPSE,
                tokens_before=tokens_before,
                tokens_after=tokens_after_cc,
            )

        # Still over — suggest session memory compaction
        if overflow_ratio >= 0.5:
            logger.warning(
                "Heavy overflow (%.0f%%). Session memory compaction recommended. "
                "Current: %d tokens, threshold: %d",
                overflow_ratio * 100,
                tokens_after_cc,
                self.auto_compact_threshold,
            )

        return CompactionResult(
            compacted=True,
            strategy=CompactionStrategy.SESSION_MEMORY,
            tokens_before=tokens_before,
            tokens_after=tokens_after_cc,
            needs_llm_compaction=True,
        )

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

        return CompactionResult(
            compacted=True,
            strategy=CompactionStrategy.FULL_LLM,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            needs_llm_compaction=tokens_after > self.auto_compact_threshold,
        )

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
                    msg.content = f"[Tool result truncated — was {original_len} chars]"
                    cleared += 1

        return cleared

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


def session_memory_compact_prompt(messages: list[Message]) -> str:
    """Generate a prompt for LLM-based session memory compaction.

    This produces a structured request for the LLM to summarize older
    messages while preserving key context.
    """
    # Format messages for the summary request
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

    conversation_text = "\n".join(formatted)

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


@dataclass
class CompactionResult:
    """Result of a compaction operation."""

    compacted: bool
    strategy: CompactionStrategy | None
    tokens_before: int
    tokens_after: int
    needs_llm_compaction: bool = False
