"""Tests for the search_issues MCP tool."""

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


async def test_search_issues_tool_exists(client: Client):
    """search_issues tool is registered in the MCP server."""
    tools = await client.list_tools()
    tool_names = [t.name for t in tools]
    assert "search_issues" in tool_names


async def test_search_issues_by_status(client: Client):
    """search_issues filters by status."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    mock_response = {
        "records": [
            {
                "id": "emodel/ept-issue@EPT-1",
                "attributes": {
                    "id": "EPT-1",
                    "summary": "Fix login bug",
                    "status": "in-progress",
                    "assignee": "admin",
                    "priority": "200_high",
                    "type": "emodel/type@ept-issue-bug",
                },
            },
        ],
    }

    with patch("servers.citeck_mcp.lib_records_query", return_value=mock_response) as mock_query, \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("search_issues", {
            "project": "COREDEV",
            "status": "in-progress",
        })

    data = result.data
    assert data["ok"] is True
    assert len(data["issues"]) == 1
    assert data["issues"][0]["id"] == "EPT-1"
    assert data["issues"][0]["summary"] == "Fix login bug"
    assert data["issues"][0]["status"] == "in-progress"
    assert data["issues"][0]["link"] == "http://localhost/v2/dashboard?recordRef=emodel/ept-issue@EPT-1"

    # Verify query predicate
    call_kwargs = mock_query.call_args[1]
    assert call_kwargs["source_id"] == "emodel/ept-issue"
    assert call_kwargs["workspaces"] == ["COREDEV"]
    query = call_kwargs["query"]
    assert query["t"] == "eq"
    assert query["att"] == "_status"
    assert query["val"] == "in-progress"


async def test_search_issues_by_assignee(client: Client):
    """search_issues filters by assignee with emodel/person@ prefix."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    mock_response = {"records": []}

    with patch("servers.citeck_mcp.lib_records_query", return_value=mock_response) as mock_query, \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        await client.call_tool("search_issues", {
            "project": "COREDEV",
            "assignee": "developer1",
        })

    call_kwargs = mock_query.call_args[1]
    query = call_kwargs["query"]
    assert query["att"] == "implementer"
    assert query["t"] == "contains"
    assert query["val"] == ["emodel/person@developer1"]


async def test_search_issues_assignee_me(client: Client):
    """search_issues resolves assignee='me' to current username."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    mock_response = {"records": []}

    with patch("servers.citeck_mcp.lib_records_query", return_value=mock_response) as mock_query, \
         patch("servers.citeck_mcp.get_username", return_value="current_user"), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("search_issues", {
            "project": "COREDEV",
            "assignee": "me",
        })

    data = result.data
    assert data["ok"] is True
    call_kwargs = mock_query.call_args[1]
    query = call_kwargs["query"]
    assert query["val"] == ["emodel/person@current_user"]


async def test_search_issues_assignee_me_fallback(client: Client):
    """search_issues returns error when 'me' cannot be resolved."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    with patch("servers.citeck_mcp.get_username", side_effect=Exception("no auth")), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("search_issues", {
            "project": "COREDEV",
            "assignee": "me",
        })

    data = result.data
    assert data["ok"] is False
    assert "current user" in data["error"].lower()


async def test_search_issues_by_type(client: Client):
    """search_issues filters by issue type using type map."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    mock_response = {"records": []}

    with patch("servers.citeck_mcp.lib_records_query", return_value=mock_response) as mock_query, \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        await client.call_tool("search_issues", {
            "project": "COREDEV",
            "type": "bug",
        })

    call_kwargs = mock_query.call_args[1]
    query = call_kwargs["query"]
    assert query["t"] == "eq"
    assert query["att"] == "_type"
    assert query["val"] == "emodel/type@ept-issue-bug"


async def test_search_issues_invalid_type(client: Client):
    """search_issues returns error for invalid issue type."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("search_issues", {
            "project": "COREDEV",
            "type": "invalid_type",
        })

    data = result.data
    assert data["ok"] is False
    assert "unknown" in data["error"].lower()
    assert "invalid_type" in data["error"].lower()


async def test_search_issues_multiple_filters(client: Client):
    """search_issues combines multiple filters with AND predicate."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    mock_response = {"records": []}

    with patch("servers.citeck_mcp.lib_records_query", return_value=mock_response) as mock_query, \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        await client.call_tool("search_issues", {
            "project": "COREDEV",
            "status": "to-do",
            "assignee": "admin",
            "type": "task",
        })

    call_kwargs = mock_query.call_args[1]
    query = call_kwargs["query"]
    assert query["t"] == "and"
    assert len(query["val"]) == 3


async def test_search_issues_pagination(client: Client):
    """search_issues respects limit parameter."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    mock_response = {"records": []}

    with patch("servers.citeck_mcp.lib_records_query", return_value=mock_response) as mock_query, \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        await client.call_tool("search_issues", {
            "project": "COREDEV",
            "limit": 5,
        })

    call_kwargs = mock_query.call_args[1]
    assert call_kwargs["page"] == {"maxItems": 5}


async def test_search_issues_sort(client: Client):
    """search_issues passes sort parameters."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    mock_response = {"records": []}

    with patch("servers.citeck_mcp.lib_records_query", return_value=mock_response) as mock_query, \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        await client.call_tool("search_issues", {
            "project": "COREDEV",
            "sort": "priority",
            "ascending": True,
        })

    call_kwargs = mock_query.call_args[1]
    assert call_kwargs["sort_by"] == [{"attribute": "priority", "ascending": True}]


async def test_search_issues_uses_default_project(client: Client):
    """search_issues uses default project when project not specified."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir, "MYPROJ")

    mock_response = {"records": []}

    with patch("servers.citeck_mcp.lib_records_query", return_value=mock_response) as mock_query, \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        await client.call_tool("search_issues", {})

    call_kwargs = mock_query.call_args[1]
    assert call_kwargs["workspaces"] == ["MYPROJ"]


async def test_search_issues_no_project(client: Client):
    """search_issues works without project (no workspace filter)."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    mock_response = {"records": []}

    with patch("servers.citeck_mcp.lib_records_query", return_value=mock_response) as mock_query, \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        await client.call_tool("search_issues", {})

    call_kwargs = mock_query.call_args[1]
    assert call_kwargs.get("workspaces") is None


async def test_search_issues_raw_query(client: Client):
    """search_issues supports raw_query dict bypassing filter building."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    mock_response = {
        "records": [
            {
                "id": "emodel/ept-issue@EPT-5",
                "attributes": {
                    "id": "EPT-5",
                    "summary": "Raw query result",
                    "status": "done",
                    "assignee": "",
                    "priority": "300_medium",
                    "type": "emodel/type@ept-issue-task",
                },
            },
        ],
    }

    raw = {"t": "eq", "att": "summary", "val": "Raw query result"}

    with patch("servers.citeck_mcp.lib_records_query", return_value=mock_response) as mock_query, \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("search_issues", {
            "project": "COREDEV",
            "raw_query": raw,
        })

    data = result.data
    assert data["ok"] is True
    call_kwargs = mock_query.call_args[1]
    assert call_kwargs["query"] == raw


async def test_search_issues_sprint_filter(client: Client):
    """search_issues filters by sprint."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    mock_response = {"records": []}

    with patch("servers.citeck_mcp.lib_records_query", return_value=mock_response) as mock_query, \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        await client.call_tool("search_issues", {
            "project": "COREDEV",
            "sprint": "emodel/ept-sprint@some-uuid",
        })

    call_kwargs = mock_query.call_args[1]
    query = call_kwargs["query"]
    assert query["t"] == "eq"
    assert query["att"] == "sprint"
    assert query["val"] == "emodel/ept-sprint@some-uuid"


async def test_search_issues_api_error(client: Client):
    """search_issues returns error on API failure."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    with patch("servers.citeck_mcp.lib_records_query",
               side_effect=RecordsApiError("HTTP 500 Server Error")), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("search_issues", {
            "project": "COREDEV",
        })

    data = result.data
    assert data["ok"] is False
    assert "500" in data["error"]


async def test_search_issues_response_format(client: Client):
    """search_issues returns issues with cleaned-up fields."""
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    mock_response = {
        "records": [
            {
                "id": "emodel/ept-issue@EPT-10",
                "attributes": {
                    "id": "EPT-10",
                    "summary": "Test issue",
                    "status": "to-do",
                    "assignee": "developer",
                    "priority": "300_medium",
                    "type": "emodel/type@ept-issue-task",
                },
            },
            {
                "id": "emodel/ept-issue@EPT-11",
                "attributes": {
                    "id": "EPT-11",
                    "summary": "Another issue",
                    "status": "in-progress",
                    "assignee": "",
                    "priority": "200_high",
                    "type": "emodel/type@ept-issue-bug",
                },
            },
        ],
    }

    with patch("servers.citeck_mcp.lib_records_query", return_value=mock_response), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("search_issues", {"project": "COREDEV"})

    data = result.data
    assert data["ok"] is True
    assert data["count"] == 2
    assert len(data["issues"]) == 2

    issue1 = data["issues"][0]
    assert issue1["id"] == "EPT-10"
    assert issue1["type"] == "task"
    assert issue1["summary"] == "Test issue"
    assert issue1["link"] == "http://localhost/v2/dashboard?recordRef=emodel/ept-issue@EPT-10"

    issue2 = data["issues"][1]
    assert issue2["id"] == "EPT-11"
    assert issue2["type"] == "bug"
    assert issue2["link"] == "http://localhost/v2/dashboard?recordRef=emodel/ept-issue@EPT-11"
