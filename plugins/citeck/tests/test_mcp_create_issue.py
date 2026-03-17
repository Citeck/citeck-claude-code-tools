"""Tests for the create_issue MCP tool."""

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


async def test_create_issue_tool_exists(client: Client):
    """create_issue tool is registered in the MCP server."""
    tools = await client.list_tools()
    tool_names = [t.name for t in tools]
    assert "create_issue" in tool_names


async def test_create_issue_preview_mode(client: Client):
    """create_issue with preview=true returns preview without creating."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    # Mock project resolution
    mock_query_response = {
        "records": [
            {"attributes": {"id": "emodel/project@proj-uuid"}},
        ],
    }
    mock_load_response = {
        "records": [
            {"attributes": {"?json": {"key": "COREDEV"}}},
        ],
    }

    with patch("servers.citeck_mcp.lib_records_query", return_value=mock_query_response), \
         patch("servers.citeck_mcp.lib_records_load", return_value=mock_load_response), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("create_issue", {
            "project": "COREDEV",
            "type": "task",
            "summary": "Test task",
            "description": "A test description",
            "preview": True,
        })

    data = result.data
    assert data["ok"] is True
    assert data["preview"] is True
    assert "record" in data
    record = data["record"]
    attrs = record["attributes"]
    assert attrs["type?str"] == "ept-issue-task"
    assert attrs["summary?str"] == "Test task"
    assert attrs["description?str"] == "A test description"
    assert attrs["_workspace?str"] == "COREDEV"
    assert attrs["link-project:project?str"] == "emodel/project@proj-uuid"
    assert attrs["_state?str"] == "submitted"
    assert attrs["priority?str"] == "300_medium"
    assert record["id"] == "emodel/ept-issue@"


async def test_create_issue_actual_create(client: Client):
    """create_issue with preview=false creates the issue."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    mock_query_response = {
        "records": [
            {"attributes": {"id": "emodel/project@proj-uuid"}},
        ],
    }
    mock_load_response = {
        "records": [
            {"attributes": {"?json": {"key": "COREDEV"}}},
        ],
    }
    mock_mutate_response = {
        "records": [
            {"id": "emodel/ept-issue@COREDEV-42"},
        ],
    }

    with patch("servers.citeck_mcp.lib_records_query", return_value=mock_query_response), \
         patch("servers.citeck_mcp.lib_records_load", return_value=mock_load_response), \
         patch("servers.citeck_mcp.lib_records_mutate", return_value=mock_mutate_response) as mock_mutate, \
         patch("servers.citeck_mcp.get_credentials", return_value={"url": "http://localhost"}), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("create_issue", {
            "project": "COREDEV",
            "type": "bug",
            "summary": "Fix login bug",
            "preview": False,
        })

    data = result.data
    assert data["ok"] is True
    assert data["id"] == "emodel/ept-issue@COREDEV-42"
    assert "link" in data
    assert "COREDEV-42" in data["link"]

    # Verify mutate was called with correct record
    call_args = mock_mutate.call_args
    records = call_args[1]["records"]
    assert len(records) == 1
    assert records[0]["id"] == "emodel/ept-issue@"
    assert records[0]["attributes"]["type?str"] == "ept-issue-bug"


async def test_create_issue_project_resolution(client: Client):
    """create_issue resolves project key to ref and workspace."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    mock_query_response = {
        "records": [
            {"attributes": {"id": "emodel/project@my-proj-uuid"}},
        ],
    }
    mock_load_response = {
        "records": [
            {"attributes": {"?json": {"key": "MYPROJ"}}},
        ],
    }

    with patch("servers.citeck_mcp.lib_records_query", return_value=mock_query_response) as mock_query, \
         patch("servers.citeck_mcp.lib_records_load", return_value=mock_load_response) as mock_load, \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("create_issue", {
            "project": "MYPROJ",
            "type": "story",
            "summary": "New feature",
            "preview": True,
        })

    data = result.data
    assert data["ok"] is True
    record = data["record"]
    assert record["attributes"]["_workspace?str"] == "MYPROJ"
    assert record["attributes"]["link-project:project?str"] == "emodel/project@my-proj-uuid"

    # Verify project query
    query_call = mock_query.call_args
    assert query_call[1]["source_id"] == "emodel/project"
    assert query_call[1]["query"]["val"] == "MYPROJ"

    # Verify load call for workspace key
    load_call = mock_load.call_args
    assert load_call[1]["record_ids"] == ["emodel/project@my-proj-uuid"]


async def test_create_issue_uses_default_project(client: Client):
    """create_issue uses default project when not specified."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir, "DEFPROJ")

    mock_query_response = {
        "records": [
            {"attributes": {"id": "emodel/project@def-uuid"}},
        ],
    }
    mock_load_response = {
        "records": [
            {"attributes": {"?json": {"key": "DEFPROJ"}}},
        ],
    }

    with patch("servers.citeck_mcp.lib_records_query", return_value=mock_query_response) as mock_query, \
         patch("servers.citeck_mcp.lib_records_load", return_value=mock_load_response), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("create_issue", {
            "type": "task",
            "summary": "Default project task",
            "preview": True,
        })

    data = result.data
    assert data["ok"] is True
    # Project query should use DEFPROJ
    query_call = mock_query.call_args
    assert query_call[1]["query"]["val"] == "DEFPROJ"


async def test_create_issue_no_project(client: Client):
    """create_issue returns error when no project specified and no default."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("create_issue", {
            "type": "task",
            "summary": "No project task",
            "preview": True,
        })

    data = result.data
    assert data["ok"] is False
    assert "project" in data["error"].lower()


async def test_create_issue_project_not_found(client: Client):
    """create_issue returns error when project key not found in Citeck."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    mock_query_response = {"records": []}

    with patch("servers.citeck_mcp.lib_records_query", return_value=mock_query_response), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("create_issue", {
            "project": "NONEXIST",
            "type": "task",
            "summary": "Test",
            "preview": True,
        })

    data = result.data
    assert data["ok"] is False
    assert "not found" in data["error"].lower()


async def test_create_issue_invalid_type(client: Client):
    """create_issue returns error for invalid issue type."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("create_issue", {
            "project": "COREDEV",
            "type": "invalid_type",
            "summary": "Test",
            "preview": True,
        })

    data = result.data
    assert data["ok"] is False
    assert "invalid_type" in data["error"].lower() or "unknown" in data["error"].lower()


async def test_create_issue_with_assignee(client: Client):
    """create_issue sets assignee with emodel/person@ prefix."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    mock_query_response = {
        "records": [{"attributes": {"id": "emodel/project@uuid"}}],
    }
    mock_load_response = {
        "records": [{"attributes": {"?json": {"key": "COREDEV"}}}],
    }

    with patch("servers.citeck_mcp.lib_records_query", return_value=mock_query_response), \
         patch("servers.citeck_mcp.lib_records_load", return_value=mock_load_response), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("create_issue", {
            "project": "COREDEV",
            "type": "task",
            "summary": "Assigned task",
            "assignee": "developer1",
            "preview": True,
        })

    data = result.data
    assert data["ok"] is True
    attrs = data["record"]["attributes"]
    assert attrs["implementer?str"] == "emodel/person@developer1"


async def test_create_issue_assignee_me(client: Client):
    """create_issue resolves assignee='me' to current username."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    mock_query_response = {
        "records": [{"attributes": {"id": "emodel/project@uuid"}}],
    }
    mock_load_response = {
        "records": [{"attributes": {"?json": {"key": "COREDEV"}}}],
    }

    with patch("servers.citeck_mcp.lib_records_query", return_value=mock_query_response), \
         patch("servers.citeck_mcp.lib_records_load", return_value=mock_load_response), \
         patch("servers.citeck_mcp.get_username", return_value="current_user"), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("create_issue", {
            "project": "COREDEV",
            "type": "task",
            "summary": "My task",
            "assignee": "me",
            "preview": True,
        })

    data = result.data
    assert data["ok"] is True
    attrs = data["record"]["attributes"]
    assert attrs["implementer?str"] == "emodel/person@current_user"


async def test_create_issue_assignee_me_failure(client: Client):
    """create_issue returns error when 'me' cannot be resolved."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    with patch("servers.citeck_mcp.get_username", side_effect=Exception("no auth")), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("create_issue", {
            "project": "COREDEV",
            "type": "task",
            "summary": "My task",
            "assignee": "me",
            "preview": True,
        })

    data = result.data
    assert data["ok"] is False
    assert "current user" in data["error"].lower()


async def test_create_issue_with_sprint(client: Client):
    """create_issue sets sprint with proper ref prefix."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    mock_query_response = {
        "records": [{"attributes": {"id": "emodel/project@uuid"}}],
    }
    mock_load_response = {
        "records": [{"attributes": {"?json": {"key": "COREDEV"}}}],
    }

    with patch("servers.citeck_mcp.lib_records_query", return_value=mock_query_response), \
         patch("servers.citeck_mcp.lib_records_load", return_value=mock_load_response), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("create_issue", {
            "project": "COREDEV",
            "type": "task",
            "summary": "Sprint task",
            "sprint": "sprint-uuid",
            "preview": True,
        })

    data = result.data
    assert data["ok"] is True
    attrs = data["record"]["attributes"]
    assert attrs["sprint?assoc"] == ["emodel/ept-sprint@sprint-uuid"]


async def test_create_issue_with_components_and_tags(client: Client):
    """create_issue sets components and tags with proper ref prefixes."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    mock_query_response = {
        "records": [{"attributes": {"id": "emodel/project@uuid"}}],
    }
    mock_load_response = {
        "records": [{"attributes": {"?json": {"key": "COREDEV"}}}],
    }

    with patch("servers.citeck_mcp.lib_records_query", return_value=mock_query_response), \
         patch("servers.citeck_mcp.lib_records_load", return_value=mock_load_response), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("create_issue", {
            "project": "COREDEV",
            "type": "task",
            "summary": "Full task",
            "components": ["comp-uuid1", "emodel/ept-components@comp-uuid2"],
            "tags": ["tag-uuid1", "emodel/ept-tags@tag-uuid2"],
            "preview": True,
        })

    data = result.data
    assert data["ok"] is True
    attrs = data["record"]["attributes"]
    assert attrs["components?assoc"] == [
        "emodel/ept-components@comp-uuid1",
        "emodel/ept-components@comp-uuid2",
    ]
    assert attrs["tags?assoc"] == [
        "emodel/ept-tags@tag-uuid1",
        "emodel/ept-tags@tag-uuid2",
    ]


async def test_create_issue_default_priority(client: Client):
    """create_issue uses 300_medium as default priority."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    mock_query_response = {
        "records": [{"attributes": {"id": "emodel/project@uuid"}}],
    }
    mock_load_response = {
        "records": [{"attributes": {"?json": {"key": "COREDEV"}}}],
    }

    with patch("servers.citeck_mcp.lib_records_query", return_value=mock_query_response), \
         patch("servers.citeck_mcp.lib_records_load", return_value=mock_load_response), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("create_issue", {
            "project": "COREDEV",
            "type": "task",
            "summary": "Task with default priority",
            "preview": True,
        })

    data = result.data
    assert data["ok"] is True
    assert data["record"]["attributes"]["priority?str"] == "300_medium"


async def test_create_issue_custom_priority(client: Client):
    """create_issue accepts custom priority."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    mock_query_response = {
        "records": [{"attributes": {"id": "emodel/project@uuid"}}],
    }
    mock_load_response = {
        "records": [{"attributes": {"?json": {"key": "COREDEV"}}}],
    }

    with patch("servers.citeck_mcp.lib_records_query", return_value=mock_query_response), \
         patch("servers.citeck_mcp.lib_records_load", return_value=mock_load_response), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("create_issue", {
            "project": "COREDEV",
            "type": "task",
            "summary": "High priority task",
            "priority": "200_high",
            "preview": True,
        })

    data = result.data
    assert data["ok"] is True
    assert data["record"]["attributes"]["priority?str"] == "200_high"


async def test_create_issue_api_error(client: Client):
    """create_issue returns error on API failure during creation."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    mock_query_response = {
        "records": [{"attributes": {"id": "emodel/project@uuid"}}],
    }
    mock_load_response = {
        "records": [{"attributes": {"?json": {"key": "COREDEV"}}}],
    }

    with patch("servers.citeck_mcp.lib_records_query", return_value=mock_query_response), \
         patch("servers.citeck_mcp.lib_records_load", return_value=mock_load_response), \
         patch("servers.citeck_mcp.lib_records_mutate",
               side_effect=RecordsApiError("HTTP 500 Server Error")), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("create_issue", {
            "project": "COREDEV",
            "type": "task",
            "summary": "Will fail",
            "preview": False,
        })

    data = result.data
    assert data["ok"] is False
    assert "500" in data["error"]


async def test_create_issue_missing_summary(client: Client):
    """create_issue requires summary parameter."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("create_issue", {
            "project": "COREDEV",
            "type": "task",
            "preview": True,
        })

    data = result.data
    assert data["ok"] is False
    assert "summary" in data["error"].lower()
