"""Tests for octopus.tools.mcp — MCP client and tool adapter."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from octopus.tools.mcp import MCPClient, MCPToolAdapter


class TestMCPClient:
    def test_initial_state(self) -> None:
        client = MCPClient("test-server")
        assert client.name == "test-server"
        assert not client.connected

    async def test_connect_stdio(self) -> None:
        client = MCPClient("test")
        await client.connect_stdio("python", ["-m", "mcp_server"])
        assert client.connected
        assert client._transport == "stdio"

    async def test_connect_http(self) -> None:
        client = MCPClient("test")
        await client.connect_http("http://localhost:8080")
        assert client.connected
        assert client._transport == "http"

    async def test_disconnect(self) -> None:
        client = MCPClient("test")
        await client.connect_http("http://localhost:8080")
        await client.disconnect()
        assert not client.connected

    async def test_list_tools_disconnected(self) -> None:
        client = MCPClient("test")
        tools = await client.list_tools()
        assert tools == []

    async def test_list_resources_disconnected(self) -> None:
        client = MCPClient("test")
        resources = await client.list_resources()
        assert resources == []

    async def test_call_tool_disconnected(self) -> None:
        client = MCPClient("test")
        with pytest.raises(RuntimeError, match="not connected"):
            await client.call_tool("tool", {})


class TestMCPToolAdapter:
    def test_adapter_properties(self) -> None:
        client = MCPClient("server1")
        tool_def = {
            "name": "read_file",
            "description": "Read a file",
            "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}},
        }
        adapter = MCPToolAdapter(client, tool_def)
        assert adapter.name == "mcp_server1_read_file"
        assert adapter.description == "Read a file"

    async def test_adapter_execute_not_implemented(self) -> None:
        from octopus.core.kernel import Context

        client = MCPClient("server1")
        await client.connect_http("http://localhost:8080")
        tool_def = {"name": "test_tool", "description": "Test"}
        adapter = MCPToolAdapter(client, tool_def)

        ctx = Context(session_id="test")
        result = await adapter.execute({}, ctx)
        assert not result.success
        assert "not connected" not in (result.error or "")  # Should say "mcp" package needed
