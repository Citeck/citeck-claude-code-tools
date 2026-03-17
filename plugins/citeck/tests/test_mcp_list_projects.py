"""Tests for the list_projects MCP tool."""

import os
import sys
import tempfile

import pytest
from unittest.mock import patch

from fastmcp import Client

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import servers.citeck_mcp as mcp_module
from servers.citeck_mcp import mcp
from lib.config import save_credentials, set_default_project, add_project
from lib.records_api import RecordsApiError


@pytest.fixture(autouse=True)
def clear_projects_cache():
    """Clear the module-level projects cache before and after each test."""
    mcp_module._projects_cache.clear()
    yield
    mcp_module._projects_cache.clear()


@pytest.fixture
async def client():
    async with Client(mcp) as c:
        yield c


def _setup_credentials(config_dir):
    """Create test credentials in a temp directory."""
    save_credentials(
        profile="default",
        url="http://localhost",
        username="admin",
        password="admin",
        client_id="sqa",
        client_secret="secret",
        auth_method="basic",
        config_dir=config_dir,
    )


async def test_list_projects_tool_exists(client: Client):
    """list_projects tool is registered in the MCP server."""
    tools = await client.list_tools()
    tool_names = [t.name for t in tools]
    assert "list_projects" in tool_names


async def test_list_projects_returns_saved(client: Client):
    """list_projects returns saved projects and default from config."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)
    add_project("COREDEV", config_dir=config_dir)
    add_project("TESTPROJ", config_dir=config_dir)
    set_default_project("COREDEV", config_dir=config_dir)

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("list_projects", {})

    data = result.data
    assert data["ok"] is True
    assert data["projects"] == ["COREDEV", "TESTPROJ"]
    assert data["default_project"] == "COREDEV"


async def test_list_projects_empty(client: Client):
    """list_projects returns empty list when no projects saved."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("list_projects", {})

    data = result.data
    assert data["ok"] is True
    assert data["projects"] == []
    assert data["default_project"] is None


async def test_list_projects_fetch_from_api(client: Client):
    """list_projects with fetch=true queries the API and caches results."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    mock_response = {
        "records": [
            {
                "id": "emodel/project@proj1",
                "attributes": {"key": "COREDEV", "name": "Core Development", "type": "emodel/type@project"},
            },
            {
                "id": "emodel/project@proj2",
                "attributes": {"key": "TESTPROJ", "name": "Test Project", "type": "emodel/type@project"},
            },
        ],
    }

    with patch("servers.citeck_mcp.lib_records_query", return_value=mock_response) as mock_query, \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("list_projects", {"fetch": True})

    data = result.data
    assert data["ok"] is True
    assert len(data["fetched_projects"]) == 2
    assert data["fetched_projects"][0]["key"] == "COREDEV"
    assert data["fetched_projects"][1]["key"] == "TESTPROJ"

    # Verify the API was called with correct source_id
    mock_query.assert_called_once()
    call_kwargs = mock_query.call_args[1]
    assert call_kwargs["source_id"] == "emodel/project"


async def test_list_projects_fetch_caches_in_memory(client: Client):
    """list_projects caches fetched projects; second call without fetch returns cached."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    mock_response = {
        "records": [
            {
                "id": "emodel/project@proj1",
                "attributes": {"key": "COREDEV", "name": "Core Development", "type": "emodel/type@project"},
            },
        ],
    }

    with patch("servers.citeck_mcp.lib_records_query", return_value=mock_response) as mock_query, \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        # First call with fetch=True populates cache
        await client.call_tool("list_projects", {"fetch": True})
        assert mock_query.call_count == 1

        # Second call without fetch still returns cached fetched_projects
        result2 = await client.call_tool("list_projects", {})
        # API should NOT have been called again
        assert mock_query.call_count == 1

    data2 = result2.data
    assert data2["ok"] is True
    assert len(data2["fetched_projects"]) == 1
    assert data2["fetched_projects"][0]["key"] == "COREDEV"


async def test_list_projects_no_set_default_param(client: Client):
    """list_projects tool does not accept set_default parameter (moved to set_project_default)."""
    tools = await client.list_tools()
    lp_tool = next(t for t in tools if t.name == "list_projects")
    param_names = list(lp_tool.inputSchema.get("properties", {}).keys())
    assert "set_default" not in param_names


async def test_set_project_default_tool_exists(client: Client):
    """set_project_default tool is registered in the MCP server."""
    tools = await client.list_tools()
    tool_names = [t.name for t in tools]
    assert "set_project_default" in tool_names


async def test_set_project_default_sets_default(client: Client):
    """set_project_default sets the default project."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)
    add_project("COREDEV", config_dir=config_dir)

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("set_project_default", {"project": "COREDEV"})

    data = result.data
    assert data["ok"] is True
    assert data["default_project"] == "COREDEV"


async def test_set_project_default_auto_adds(client: Client):
    """set_project_default auto-adds the project to the saved list."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("set_project_default", {"project": "NEWPROJ"})

    data = result.data
    assert data["ok"] is True
    assert "NEWPROJ" in data["projects"]
    assert data["default_project"] == "NEWPROJ"


async def test_list_projects_fetch_cache_keyed_by_profile(client: Client):
    """list_projects caches fetched projects per profile; different profiles get separate caches."""
    config_dir = tempfile.mkdtemp()
    # Set up two profiles
    _setup_credentials(config_dir)  # "default" profile
    save_credentials(
        profile="staging",
        url="http://staging",
        username="staging_user",
        password="pass",
        client_id="sqa",
        client_secret="secret",
        auth_method="basic",
        config_dir=config_dir,
    )
    # Set up different saved projects per profile
    add_project("COREDEV", profile="default", config_dir=config_dir)
    set_default_project("COREDEV", profile="default", config_dir=config_dir)
    add_project("STAGE-PROJ", profile="staging", config_dir=config_dir)
    set_default_project("STAGE-PROJ", profile="staging", config_dir=config_dir)

    mock_response_default = {
        "records": [
            {
                "id": "emodel/project@proj1",
                "attributes": {"key": "COREDEV", "name": "Core Development", "type": "emodel/type@project"},
            },
        ],
    }
    mock_response_staging = {
        "records": [
            {
                "id": "emodel/project@proj2",
                "attributes": {"key": "STAGING", "name": "Staging Project", "type": "emodel/type@project"},
            },
        ],
    }

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        # Fetch with default profile
        with patch("servers.citeck_mcp.lib_records_query", return_value=mock_response_default), \
             patch("servers.citeck_mcp.get_active_profile", return_value="default"):
            await client.call_tool("list_projects", {"fetch": True})

        # Fetch with staging profile
        with patch("servers.citeck_mcp.lib_records_query", return_value=mock_response_staging), \
             patch("servers.citeck_mcp.get_active_profile", return_value="staging"):
            await client.call_tool("list_projects", {"fetch": True})

        # Verify each profile has its own cached data
        with patch("servers.citeck_mcp.get_active_profile", return_value="default"):
            result_default = await client.call_tool("list_projects", {})
        with patch("servers.citeck_mcp.get_active_profile", return_value="staging"):
            result_staging = await client.call_tool("list_projects", {})

    # Default profile: fetched_projects, saved projects, and default_project all from "default"
    assert result_default.data["fetched_projects"][0]["key"] == "COREDEV"
    assert result_default.data["projects"] == ["COREDEV"]
    assert result_default.data["default_project"] == "COREDEV"
    # Staging profile: fetched_projects, saved projects, and default_project all from "staging"
    assert result_staging.data["fetched_projects"][0]["key"] == "STAGING"
    assert result_staging.data["projects"] == ["STAGE-PROJ"]
    assert result_staging.data["default_project"] == "STAGE-PROJ"


async def test_list_projects_fetch_api_error(client: Client):
    """list_projects returns error when API fetch fails."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    with patch("servers.citeck_mcp.lib_records_query",
               side_effect=RecordsApiError("HTTP 500 Server Error")), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("list_projects", {"fetch": True})

    data = result.data
    assert data["ok"] is False
    assert "500" in data["error"]


async def test_set_project_default_empty_key(client: Client):
    """set_project_default rejects empty and whitespace-only keys."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result_empty = await client.call_tool("set_project_default", {"project": ""})
        result_whitespace = await client.call_tool("set_project_default", {"project": "   "})

    assert result_empty.data["ok"] is False
    assert "empty" in result_empty.data["error"].lower()
    assert result_whitespace.data["ok"] is False
    assert "empty" in result_whitespace.data["error"].lower()


async def test_set_project_default_uses_profile_snapshot(client: Client):
    """set_project_default passes the snapshotted profile to config functions."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)
    add_project("PROJ1", profile="default", config_dir=config_dir)

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.get_active_profile", return_value="default") as mock_profile, \
         patch("servers.citeck_mcp.set_default_project") as mock_set, \
         patch("servers.citeck_mcp.get_projects", return_value=["PROJ1"]) as mock_get:
        await client.call_tool("set_project_default", {"project": "PROJ1"})

    mock_profile.assert_called_once_with(config_dir)
    mock_set.assert_called_once_with("PROJ1", profile="default", config_dir=config_dir)
    mock_get.assert_called_once_with(profile="default", config_dir=config_dir)


async def test_list_projects_fetch_forwards_profile_to_api(client: Client):
    """list_projects passes the snapshotted profile to lib_records_query."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    mock_response = {"records": []}

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.get_active_profile", return_value="default"), \
         patch("servers.citeck_mcp.lib_records_query", return_value=mock_response) as mock_query:
        await client.call_tool("list_projects", {"fetch": True})

    mock_query.assert_called_once()
    call_kwargs = mock_query.call_args[1]
    assert call_kwargs["profile"] == "default"
    assert call_kwargs["config_dir"] == config_dir
