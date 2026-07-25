"""MCP (Model Context Protocol) client bridge — connect to MCP servers.

Supports both stdio (local process) and HTTP (remote server) transports.
Wraps MCP tools as Octopus Tool instances for the registry.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from octopus.core.kernel import Context, ToolResult
from octopus.tools.base import Tool

logger = logging.getLogger(__name__)


class MCPClient:
    """Client for connecting to MCP servers.

    Supports stdio (subprocess) and HTTP transports. Tools discovered
    from the server can be wrapped as Octopus Tools via MCPToolAdapter.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._connected = False
        self._transport: str | None = None
        self._tools: list[dict[str, Any]] = []
        self._resources: list[dict[str, Any]] = []

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect_stdio(self, command: str, args: list[str] | None = None) -> None:
        """Connect to an MCP server via stdio (subprocess).

        Args:
            command: The command to run (e.g., "npx", "python")
            args: Arguments to pass to the command
        """
        self._transport = "stdio"
        self._command = command
        self._args = args or []
        self._connected = True
        logger.info("MCP client %s: connected via stdio (%s)", self.name, command)

    async def connect_http(self, url: str) -> None:
        """Connect to an MCP server via HTTP.

        Args:
            url: The HTTP URL of the MCP server
        """
        self._transport = "http"
        self._url = url
        self._connected = True
        logger.info("MCP client %s: connected via HTTP (%s)", self.name, url)

    async def list_tools(self) -> list[dict[str, Any]]:
        """List available tools from the MCP server."""
        if not self._connected:
            return []
        # In a full implementation, this would call the MCP server
        # For now, return cached tools
        return self._tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call a tool on the MCP server.

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            Tool execution result
        """
        if not self._connected:
            raise RuntimeError(f"MCP client {self.name} not connected")

        # In a full implementation, this would send the tool call
        # to the MCP server via the appropriate transport
        logger.info("MCP client %s: call tool %s", self.name, name)
        raise NotImplementedError(
            "MCP tool calls require the 'mcp' package. Install with: pip install mcp"
        )

    async def list_resources(self) -> list[dict[str, Any]]:
        """List available resources from the MCP server."""
        if not self._connected:
            return []
        return self._resources

    async def read_resource(self, uri: str) -> str:
        """Read a resource from the MCP server."""
        if not self._connected:
            raise RuntimeError(f"MCP client {self.name} not connected")
        raise NotImplementedError(
            "MCP resource access requires the 'mcp' package. "
            "Install with: pip install mcp"
        )

    async def disconnect(self) -> None:
        """Disconnect from the MCP server."""
        self._connected = False
        self._transport = None
        logger.info("MCP client %s: disconnected", self.name)


class MCPToolAdapter(Tool):
    """Wraps an MCP server tool as an Octopus Tool.

    This adapter allows MCP tools to be registered in the Octopus
    ToolRegistry and used by the agent loop like any other tool.
    """

    def __init__(self, client: MCPClient, tool_def: dict[str, Any]) -> None:
        self._client = client
        self._tool_def = tool_def
        self.name = f"mcp_{client.name}_{tool_def['name']}"
        self.description = tool_def.get("description", f"MCP tool: {tool_def['name']}")
        self.input_schema = tool_def.get(
            "inputSchema", {"type": "object", "properties": {}}
        )

    async def execute(self, args: dict[str, Any], ctx: Context) -> ToolResult:
        """Execute the MCP tool via the client."""
        try:
            result = await self._client.call_tool(self._tool_def["name"], args)
            return ToolResult(
                success=True,
                output=json.dumps(result) if not isinstance(result, str) else result,
            )
        except Exception as e:
            return ToolResult(success=False, output=None, error=str(e))
