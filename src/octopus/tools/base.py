"""Tool protocol and registry."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol

from octopus.core.kernel import Context, ToolResult


# ---------------------------------------------------------------------------
# Tool protocol
# ---------------------------------------------------------------------------

class Tool(Protocol):
    """Protocol that all tools must implement."""

    name: str
    description: str
    input_schema: Dict[str, Any]

    async def execute(self, args: Dict[str, Any], ctx: Context) -> ToolResult: ...


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

class ToolRegistry:
    """Registry for discovering and managing tools."""

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_names(self) -> List[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def list_definitions(self) -> List[Dict[str, Any]]:
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
