"""Octopus Agent Loop -- agent loop engine, context management, and compaction."""

from .compaction import (
    CompactionEngine,
    CompactionResult,
    CompactionStrategy,
    MicrocompactConfig,
)
from .context import ConversationContext
from .engine import run_query
from .models import (
    CompactBoundaryData,
    Message,
    Role,
    StreamEvent,
    StreamEventType,
    ToolCallDelta,
)

__all__ = [
    "run_query",
    "Message",
    "Role",
    "StreamEvent",
    "StreamEventType",
    "ToolCallDelta",
    "ConversationContext",
    "CompactionEngine",
    "CompactionResult",
    "CompactionStrategy",
    "MicrocompactConfig",
    "CompactBoundaryData",
]
