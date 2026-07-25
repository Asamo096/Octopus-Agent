"""Octopus Agent Loop — agent loop engine, context management, and compaction."""

from .compaction import CompactionEngine, CompactionStrategy
from .context import ConversationContext
from .engine import run_query
from .models import Message, Role, StreamEvent, StreamEventType, ToolCallDelta

__all__ = [
    "run_query",
    "Message",
    "Role",
    "StreamEvent",
    "StreamEventType",
    "ToolCallDelta",
    "ConversationContext",
    "CompactionEngine",
    "CompactionStrategy",
]
