"""Tests for the test_connection MCP tool."""

import os
import sys
import tempfile

import pytest
from unittest.mock import patch
from fastmcp import Client

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from servers.citeck_mcp import mcp
from lib.config import save_credentials


@pytest.fixture
async def client():
    async with Client(mcp) as c:
        yield c


def _setup_credentials(config_dir, auth_method="oidc"):
    """Create test credentials in a temp directory."""
    save_credentials(
        profile="default",
        url="http://localhost",
        username="admin",
        password="admin",
        client_id="sqa",
        client_secret="secret",
        auth_method=auth_method,
        config_dir=config_dir,
    )


async def test_test_connection_tool_exists(client: Client):
    """test_connection tool is registered in the MCP server."""
    tools = await client.list_tools()
    tool_names = [t.name for t in tools]
    assert "test_connection" in tool_names


async def test_test_connection_success(client: Client):
    """test_connection returns ok=True with method and username on success."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    mock_validate = {"ok": True, "method": "oidc", "error": None}

    with patch("servers.citeck_mcp.validate_connection", return_value=mock_validate), \
         patch("servers.citeck_mcp.get_username", return_value="admin"), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("test_connection", {})

    data = result.data
    assert data["ok"] is True
    assert data["method"] == "oidc"
    assert data["username"] == "admin"
    assert data["url"] == "http://localhost"


async def test_test_connection_auth_failure(client: Client):
    """test_connection returns ok=False with error on auth failure."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    mock_validate = {"ok": False, "method": "oidc", "error": "HTTP 401 Unauthorized"}

    with patch("servers.citeck_mcp.validate_connection", return_value=mock_validate), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("test_connection", {})

    data = result.data
    assert data["ok"] is False
    assert data["error"] == "HTTP 401 Unauthorized"


async def test_test_connection_no_credentials(client: Client):
    """test_connection returns ok=False when no credentials configured."""
    config_dir = tempfile.mkdtemp()

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("test_connection", {})

    data = result.data
    assert data["ok"] is False
    assert "error" in data
    assert "No credentials" in data["error"] or "not configured" in data["error"]


async def test_test_connection_basic_auth(client: Client):
    """test_connection works with basic auth method."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir, auth_method="basic")

    mock_validate = {"ok": True, "method": "basic", "error": None}

    with patch("servers.citeck_mcp.validate_connection", return_value=mock_validate), \
         patch("servers.citeck_mcp.get_username", return_value="admin"), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("test_connection", {})

    data = result.data
    assert data["ok"] is True
    assert data["method"] == "basic"
    assert data["username"] == "admin"
