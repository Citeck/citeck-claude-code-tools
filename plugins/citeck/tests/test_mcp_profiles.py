"""Tests for the MCP tools list_profiles and set_active_profile."""

import os
import shutil
import sys
import tempfile

import pytest
from unittest.mock import patch
from fastmcp import Client

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from servers.citeck_mcp import mcp
from lib import config


@pytest.fixture
async def client():
    async with Client(mcp) as c:
        yield c


@pytest.fixture
def config_dir():
    d = tempfile.mkdtemp()
    config.save_credentials(
        profile="local",
        url="http://localhost",
        username="admin",
        password="admin",
        auth_method="oidc",
        config_dir=d,
    )
    config.save_credentials(
        profile="prod",
        url="https://citeck.example.com",
        username="u",
        password="p",
        auth_method="oidc",
        config_dir=d,
    )
    yield d
    shutil.rmtree(d, ignore_errors=True)


async def test_profile_tools_registered(client: Client):
    tools = await client.list_tools()
    names = [t.name for t in tools]
    assert "list_profiles" in names
    assert "set_active_profile" in names


async def test_list_profiles_returns_metadata(client: Client, config_dir: str):
    config.set_active_profile("local", config_dir)
    config.set_docs_profile("prod", config_dir)
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("list_profiles", {})

    data = result.data
    assert data["ok"] is True
    assert data["active"] == "local"
    assert data["docs_profile"] == "prod"

    by_name = {p["name"]: p for p in data["profiles"]}
    assert set(by_name.keys()) == {"local", "prod"}

    assert by_name["local"]["url"] == "http://localhost"
    assert by_name["local"]["auth_method"] == "oidc"
    assert by_name["local"]["is_active"] is True
    assert by_name["local"]["is_docs"] is False

    assert by_name["prod"]["url"] == "https://citeck.example.com"
    assert by_name["prod"]["is_active"] is False
    assert by_name["prod"]["is_docs"] is True

    # Sensitive fields must never leak.
    for p in data["profiles"]:
        assert "password" not in p
        assert "client_secret" not in p


async def test_list_profiles_empty(client: Client):
    empty_dir = tempfile.mkdtemp()
    try:
        with patch("servers.citeck_mcp._get_config_dir", return_value=empty_dir):
            result = await client.call_tool("list_profiles", {})
        data = result.data
        assert data["ok"] is True
        assert data["profiles"] == []
        assert data["active"] == "default"
        assert data["docs_profile"] is None
    finally:
        shutil.rmtree(empty_dir, ignore_errors=True)


async def test_set_active_profile_success(client: Client, config_dir: str):
    config.set_active_profile("local", config_dir)
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("set_active_profile", {"profile": "prod"})

    data = result.data
    assert data["ok"] is True
    assert data["active_profile"] == "prod"
    assert data["server"] == "https://citeck.example.com"
    assert data["auth_method"] == "oidc"
    assert config.get_active_profile(config_dir) == "prod"


async def test_set_active_profile_rejects_unknown(client: Client, config_dir: str):
    config.set_active_profile("local", config_dir)
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("set_active_profile", {"profile": "ghost"})
    data = result.data
    assert data["ok"] is False
    assert "ghost" in data["error"]
    # Active profile must remain unchanged on failure.
    assert config.get_active_profile(config_dir) == "local"


async def test_set_active_profile_rejects_path_traversal(client: Client, config_dir: str):
    config.set_active_profile("local", config_dir)
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("set_active_profile", {"profile": "../secret"})
    data = result.data
    assert data["ok"] is False
    err = data["error"].lower()
    assert "invalid" in err or "../secret" in data["error"]
    # Active profile must remain unchanged on rejection.
    assert config.get_active_profile(config_dir) == "local"


async def test_set_active_profile_rejects_empty(client: Client, config_dir: str):
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("set_active_profile", {"profile": ""})
    data = result.data
    assert data["ok"] is False
    assert "required" in data["error"].lower()


async def test_set_active_profile_rejects_whitespace(client: Client, config_dir: str):
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("set_active_profile", {"profile": "   "})
    data = result.data
    assert data["ok"] is False
    assert "required" in data["error"].lower()
