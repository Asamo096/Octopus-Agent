"""Tool protocol and registry."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from octopus.core.kernel import Context, ToolResult

# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    """Result of input validation."""

    valid: bool
    error_message: str | None = None
    error_code: int | None = None


# ---------------------------------------------------------------------------
# Tool protocol
# ---------------------------------------------------------------------------


class Tool(Protocol):
    """Protocol that all tools must implement."""

    name: str
    description: str
    input_schema: dict[str, Any]

    # Classification flags (optional with defaults)
    is_read_only: bool = False
    is_destructive: bool = False
    is_concurrency_safe: bool = False
    max_result_size_chars: int = 100_000
    interrupt_behavior: str = "block"

    async def execute(self, args: dict[str, Any], ctx: Context) -> ToolResult: ...

    def validate_input(self, **kwargs: Any) -> ValidationResult:
        """Validate input arguments. Default returns valid."""
        return ValidationResult(valid=True)

    def get_activity_description(self, **kwargs: Any) -> str | None:
        """Get a human-readable description of the current activity."""
        return None


# ---------------------------------------------------------------------------
# Result size enforcement
# ---------------------------------------------------------------------------

# Default directory for persisted tool results
_RESULT_CACHE_DIR = Path(tempfile.gettempdir()) / "octopus" / "tool_results"


def enforce_result_size(result: ToolResult, tool: Tool) -> ToolResult:
    """Persist large tool results to disk if they exceed the tool's max_result_size_chars.

    When the result output exceeds the limit, it is written to a temp file and
    the ToolResult output is replaced with a pointer message including the file path.
    """
    if result.output is None:
        return result

    max_chars = getattr(tool, "max_result_size_chars", 100_000)

    # Serialize output to check size
    if isinstance(result.output, str):
        output_str = result.output
    else:
        output_str = json.dumps(result.output, default=str)

    if len(output_str) <= max_chars:
        return result

    # Persist to disk
    _RESULT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = _RESULT_CACHE_DIR / f"{tool.name}_{id(result)}.txt"
    cache_file.write_text(output_str, encoding="utf-8")

    truncated_preview = output_str[:500]
    new_output = (
        f"[Result too large ({len(output_str)} chars, limit {max_chars}). "
        f"Persisted to: {cache_file}]\n"
        f"Preview (first 500 chars):\n{truncated_preview}"
    )

    metadata = dict(result.metadata) if result.metadata else {}
    metadata["persisted_to"] = str(cache_file)
    metadata["original_size_chars"] = len(output_str)
    metadata["truncated"] = True

    return ToolResult(
        success=result.success,
        output=new_output,
        error=result.error,
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------


class ToolRegistry:
    """Registry for discovering and managing tools."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_names(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def list_definitions(self) -> list[dict[str, Any]]:
        """List tool definitions for the LLM provider (function calling format)."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.input_schema,
                },
            }
            for t in self._tools.values()
        ]

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
