"""Tests for the reauthenticate MCP tool."""

import os
import sys
import tempfile
import time

import pytest
from unittest.mock import patch
from fastmcp import Client

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from servers.citeck_mcp import mcp
from lib.config import save_credentials
from lib.auth import AuthError, _load_cache

TOKEN_ENDPOINT = "https://eis.example.com/auth/realms/Test/protocol/openid-connect/token"
AUTH_ENDPOINT = "https://eis.example.com/auth/realms/Test/protocol/openid-connect/auth"


@pytest.fixture
async def client():
    async with Client(mcp) as c:
        yield c


def _setup_pkce_profile(config_dir, with_endpoints=True):
    kwargs = {
        "profile": "default",
        "url": "http://localhost",
        "client_id": "citeck-ai-agent",
        "auth_method": "oidc-pkce",
        "config_dir": config_dir,
    }
    if with_endpoints:
        kwargs["token_endpoint"] = TOKEN_ENDPOINT
        kwargs["authorization_endpoint"] = AUTH_ENDPOINT
    save_credentials(**kwargs)


def _make_tokens():
    return {
        "access_token": "new-at",
        "refresh_token": "new-rt",
        "access_expires_at": time.time() + 300,
        "refresh_expires_at": None,
    }


async def test_reauthenticate_tool_exists(client: Client):
    """reauthenticate tool is registered in the MCP server."""
    tools = await client.list_tools()
    tool_names = [t.name for t in tools]
    assert "reauthenticate" in tool_names


async def test_reauthenticate_success(client: Client):
    """Runs the PKCE flow with stored endpoints and saves tokens."""
    config_dir = tempfile.mkdtemp()
    _setup_pkce_profile(config_dir)

    with patch("lib.pkce.authorize", return_value=_make_tokens()) as mock_auth, \
         patch("servers.citeck_mcp.get_username", return_value="admin"), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("reauthenticate", {})

    data = result.data
    assert data["ok"] is True
    assert data["profile"] == "default"
    assert data["username"] == "admin"
    assert data["url"] == "http://localhost"

    args = mock_auth.call_args[0]
    assert args[0] == TOKEN_ENDPOINT
    assert args[1] == AUTH_ENDPOINT
    assert args[2] == "citeck-ai-agent"

    cache = _load_cache("default", config_dir=config_dir)
    assert cache["access_token"] == "new-at"
    assert cache["refresh_expires_at"] is None


async def test_reauthenticate_rediscovers_endpoints(client: Client):
    """Falls back to endpoint discovery when the profile has none stored."""
    config_dir = tempfile.mkdtemp()
    _setup_pkce_profile(config_dir, with_endpoints=False)

    eis_info = {"eis_id": "eis.example.com", "realm": "Test", "is_oidc": True}
    endpoints = {"token_endpoint": TOKEN_ENDPOINT,
                 "authorization_endpoint": AUTH_ENDPOINT}

    with patch("lib.pkce.authorize", return_value=_make_tokens()) as mock_auth, \
         patch("lib.auth.discover_eis", return_value=eis_info), \
         patch("lib.auth.discover_oidc_endpoints", return_value=endpoints), \
         patch("servers.citeck_mcp.get_username", return_value="admin"), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("reauthenticate", {})

    assert result.data["ok"] is True
    args = mock_auth.call_args[0]
    assert args[0] == TOKEN_ENDPOINT
    assert args[1] == AUTH_ENDPOINT


async def test_reauthenticate_refuses_basic_profile(client: Client):
    """Non-PKCE profiles do not need browser re-auth."""
    config_dir = tempfile.mkdtemp()
    save_credentials(
        profile="default",
        url="http://localhost",
        username="admin",
        password="admin",
        auth_method="basic",
        config_dir=config_dir,
    )

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("reauthenticate", {})

    data = result.data
    assert data["ok"] is False
    assert "basic" in data["error"]
    assert "citeck-auth" in data["error"]


async def test_reauthenticate_no_credentials(client: Client):
    """Returns an error when the profile is not configured."""
    config_dir = tempfile.mkdtemp()

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("reauthenticate", {})

    data = result.data
    assert data["ok"] is False
    assert "No credentials" in data["error"]


async def test_reauthenticate_timeout(client: Client):
    """Browser-flow timeout surfaces as ok=False with the error message."""
    config_dir = tempfile.mkdtemp()
    _setup_pkce_profile(config_dir)

    with patch("lib.pkce.authorize",
               side_effect=AuthError("Timed out waiting for browser callback")), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("reauthenticate", {})

    data = result.data
    assert data["ok"] is False
    assert "Timed out" in data["error"]
