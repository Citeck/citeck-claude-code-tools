"""Tests for metadata query MCP tools: query_sprints, query_components, query_tags, query_releases."""

import os
import sys
import tempfile

import pytest
from unittest.mock import patch

from fastmcp import Client

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from servers.citeck_mcp import mcp
from lib.config import save_credentials, set_default_project, add_project
from lib.records_api import RecordsApiError


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


def _setup_with_default_project(config_dir, project="COREDEV"):
    """Create credentials and set a default project."""
    _setup_credentials(config_dir)
    add_project(project, config_dir=config_dir)
    set_default_project(project, config_dir=config_dir)


# --- Tool registration tests ---


async def test_query_sprints_tool_exists(client: Client):
    """query_sprints tool is registered."""
    tools = await client.list_tools()
    tool_names = [t.name for t in tools]
    assert "query_sprints" in tool_names


async def test_query_components_tool_exists(client: Client):
    """query_components tool is registered."""
    tools = await client.list_tools()
    tool_names = [t.name for t in tools]
    assert "query_components" in tool_names


async def test_query_tags_tool_exists(client: Client):
    """query_tags tool is registered."""
    tools = await client.list_tools()
    tool_names = [t.name for t in tools]
    assert "query_tags" in tool_names


async def test_query_releases_tool_exists(client: Client):
    """query_releases tool is registered."""
    tools = await client.list_tools()
    tool_names = [t.name for t in tools]
    assert "query_releases" in tool_names


# --- query_sprints tests ---


async def test_query_sprints_basic(client: Client):
    """query_sprints returns formatted sprint records."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    mock_response = {
        "records": [
            {
                "id": "emodel/ept-sprint@uuid1",
                "attributes": {
                    "name": "Sprint 1",
                    "status": {"value": "in-progress", "disp": "In Progress"},
                    "startDate": "2026-01-01",
                    "endDate": "2026-01-14",
                    "created": "2026-01-01T00:00:00Z",
                },
            },
            {
                "id": "emodel/ept-sprint@uuid2",
                "attributes": {
                    "name": "Sprint 2",
                    "status": {"value": "new", "disp": "New"},
                    "startDate": "2026-01-15",
                    "endDate": "2026-01-28",
                    "created": "2026-01-15T00:00:00Z",
                },
            },
        ]
    }

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.lib_records_query", return_value=mock_response) as mock_query:
        result = await client.call_tool("query_sprints", {"project": "COREDEV"})

    data = result.data
    assert data["ok"] is True
    assert data["total"] == 2
    assert len(data["records"]) == 2
    assert data["records"][0]["name"] == "Sprint 1"
    assert data["records"][0]["status"] == "In Progress"

    # Verify query was called with correct source_id and type filter
    call_kwargs = mock_query.call_args[1]
    assert call_kwargs["source_id"] == "emodel/ept-sprint"
    assert call_kwargs["workspaces"] == ["COREDEV"]


async def test_query_sprints_with_status_filter(client: Client):
    """query_sprints filters by status."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    mock_response = {"records": []}

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.lib_records_query", return_value=mock_response) as mock_query:
        result = await client.call_tool("query_sprints", {"project": "COREDEV", "status": "in-progress"})

    data = result.data
    assert data["ok"] is True

    # Verify status filter is included in query
    call_kwargs = mock_query.call_args[1]
    query = call_kwargs["query"]
    assert query["t"] == "and"
    status_pred = [p for p in query["val"] if p.get("att") == "_status"]
    assert len(status_pred) == 1
    assert status_pred[0]["val"] == "in-progress"


async def test_query_sprints_uses_default_project(client: Client):
    """query_sprints uses default project when none specified."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir, "MYPROJ")

    mock_response = {"records": []}

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.lib_records_query", return_value=mock_response) as mock_query:
        await client.call_tool("query_sprints", {})

    call_kwargs = mock_query.call_args[1]
    assert call_kwargs["workspaces"] == ["MYPROJ"]


async def test_query_sprints_no_project(client: Client):
    """query_sprints returns error when no project available."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("query_sprints", {})

    data = result.data
    assert data["ok"] is False
    assert "project" in data["error"].lower()


async def test_query_sprints_api_error(client: Client):
    """query_sprints handles RecordsApiError."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.lib_records_query", side_effect=RecordsApiError("Connection failed")):
        result = await client.call_tool("query_sprints", {"project": "COREDEV"})

    data = result.data
    assert data["ok"] is False
    assert "Connection failed" in data["error"]


# --- query_components tests ---


async def test_query_components_basic(client: Client):
    """query_components returns formatted component records."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    mock_response = {
        "records": [
            {
                "id": "emodel/ept-components@uuid1",
                "attributes": {
                    "name": "Backend",
                    "creator": {"id": "admin", "disp": "Admin User"},
                    "created": "2026-01-01T00:00:00Z",
                },
            },
        ]
    }

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.lib_records_query", return_value=mock_response) as mock_query:
        result = await client.call_tool("query_components", {"project": "COREDEV"})

    data = result.data
    assert data["ok"] is True
    assert data["total"] == 1
    assert data["records"][0]["name"] == "Backend"

    call_kwargs = mock_query.call_args[1]
    assert call_kwargs["source_id"] == "emodel/ept-components"


async def test_query_components_uses_default_project(client: Client):
    """query_components uses default project."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir, "TEST")

    mock_response = {"records": []}

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.lib_records_query", return_value=mock_response) as mock_query:
        await client.call_tool("query_components", {})

    call_kwargs = mock_query.call_args[1]
    assert call_kwargs["workspaces"] == ["TEST"]


async def test_query_components_no_project(client: Client):
    """query_components returns error when no project available."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("query_components", {})

    data = result.data
    assert data["ok"] is False


# --- query_tags tests ---


async def test_query_tags_basic(client: Client):
    """query_tags returns formatted tag records."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    mock_response = {
        "records": [
            {
                "id": "emodel/ept-tags@uuid1",
                "attributes": {
                    "name": "frontend",
                    "creator": {"id": "admin", "disp": "Admin"},
                    "created": "2026-02-01T00:00:00Z",
                },
            },
            {
                "id": "emodel/ept-tags@uuid2",
                "attributes": {
                    "name": "urgent",
                    "creator": {"id": "user1", "disp": "User One"},
                    "created": "2026-02-10T00:00:00Z",
                },
            },
        ]
    }

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.lib_records_query", return_value=mock_response) as mock_query:
        result = await client.call_tool("query_tags", {"project": "COREDEV"})

    data = result.data
    assert data["ok"] is True
    assert data["total"] == 2
    assert data["records"][0]["name"] == "frontend"
    assert data["records"][1]["name"] == "urgent"

    call_kwargs = mock_query.call_args[1]
    assert call_kwargs["source_id"] == "emodel/ept-tags"


async def test_query_tags_no_project(client: Client):
    """query_tags returns error when no project available."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("query_tags", {})

    data = result.data
    assert data["ok"] is False


# --- query_releases tests ---


async def test_query_releases_basic(client: Client):
    """query_releases returns formatted release records."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    mock_response = {
        "records": [
            {
                "id": "emodel/ecos-release-type@uuid1",
                "attributes": {
                    "name": "v1.0.0",
                    "status": {"value": "completed", "disp": "Completed"},
                    "startDate": "2026-01-01",
                    "releaseDate": "2026-02-01",
                    "implementer": {"disp": "Admin", "value": "emodel/person@admin"},
                    "created": "2026-01-01T00:00:00Z",
                },
            },
        ]
    }

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.lib_records_query", return_value=mock_response) as mock_query:
        result = await client.call_tool("query_releases", {"project": "COREDEV"})

    data = result.data
    assert data["ok"] is True
    assert data["total"] == 1
    assert data["records"][0]["name"] == "v1.0.0"
    assert data["records"][0]["status"] == "Completed"

    call_kwargs = mock_query.call_args[1]
    assert call_kwargs["source_id"] == "emodel/ecos-release-type"


async def test_query_releases_with_status_filter(client: Client):
    """query_releases filters by status."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    mock_response = {"records": []}

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.lib_records_query", return_value=mock_response) as mock_query:
        await client.call_tool("query_releases", {"project": "COREDEV", "status": "completed"})

    call_kwargs = mock_query.call_args[1]
    query = call_kwargs["query"]
    assert query["t"] == "and"
    status_pred = [p for p in query["val"] if p.get("att") == "_status"]
    assert len(status_pred) == 1
    assert status_pred[0]["val"] == "completed"


async def test_query_releases_uses_default_project(client: Client):
    """query_releases uses default project."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir, "RELEASE")

    mock_response = {"records": []}

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.lib_records_query", return_value=mock_response) as mock_query:
        await client.call_tool("query_releases", {})

    call_kwargs = mock_query.call_args[1]
    assert call_kwargs["workspaces"] == ["RELEASE"]


async def test_query_releases_no_project(client: Client):
    """query_releases returns error when no project available."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("query_releases", {})

    data = result.data
    assert data["ok"] is False


async def test_query_releases_api_error(client: Client):
    """query_releases handles RecordsApiError."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.lib_records_query", side_effect=RecordsApiError("Timeout")):
        result = await client.call_tool("query_releases", {"project": "COREDEV"})

    data = result.data
    assert data["ok"] is False
    assert "Timeout" in data["error"]
