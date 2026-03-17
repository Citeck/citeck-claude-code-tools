"""Tests for the Citeck MCP server skeleton."""

import pytest
from fastmcp import Client

from servers.citeck_mcp import mcp


@pytest.fixture
async def client():
    async with Client(mcp) as c:
        yield c


async def test_server_imports():
    """MCP server module imports correctly and mcp instance exists."""
    assert mcp is not None
    assert mcp.name == "citeck"


async def test_ping_tool_exists(client: Client):
    """Ping tool is registered in the MCP server."""
    tools = await client.list_tools()
    tool_names = [t.name for t in tools]
    assert "ping" in tool_names


async def test_ping_tool_returns_ok(client: Client):
    """Ping tool returns {ok: True}."""
    result = await client.call_tool("ping", {})
    assert result.data == {"ok": True}
