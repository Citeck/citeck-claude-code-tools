"""Tests for the update_issue MCP tool."""

import os
import sys
import tempfile

import pytest
from unittest.mock import patch

from fastmcp import Client

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from servers.citeck_mcp import mcp
from lib.config import save_credentials
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


async def test_update_issue_tool_exists(client: Client):
    """update_issue tool is registered in the MCP server."""
    tools = await client.list_tools()
    tool_names = [t.name for t in tools]
    assert "update_issue" in tool_names


async def test_update_issue_preview_mode(client: Client):
    """update_issue with preview=true returns preview without updating."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("update_issue", {
            "issue": "COREDEV-42",
            "status": "in-progress",
            "preview": True,
        })

    data = result.data
    assert data["ok"] is True
    assert data["preview"] is True
    record = data["record"]
    assert record["id"] == "emodel/ept-issue@COREDEV-42"
    attrs = record["attributes"]
    assert attrs["_state?str"] == "in-progress"
    assert attrs["_workspace?str"] == "COREDEV"


async def test_update_issue_actual_update(client: Client):
    """update_issue with preview=false performs the mutation."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    mock_mutate_response = {
        "records": [
            {"id": "emodel/ept-issue@COREDEV-42"},
        ],
    }

    with patch("servers.citeck_mcp.lib_records_mutate", return_value=mock_mutate_response) as mock_mutate, \
         patch("servers.citeck_mcp.get_credentials", return_value={"url": "http://localhost"}), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("update_issue", {
            "issue": "COREDEV-42",
            "status": "done",
            "preview": False,
        })

    data = result.data
    assert data["ok"] is True
    assert data["id"] == "emodel/ept-issue@COREDEV-42"
    assert "link" in data

    # Verify mutate was called correctly
    call_args = mock_mutate.call_args
    records = call_args[1]["records"]
    assert len(records) == 1
    assert records[0]["id"] == "emodel/ept-issue@COREDEV-42"
    assert records[0]["attributes"]["_state?str"] == "done"
    assert records[0]["attributes"]["_workspace?str"] == "COREDEV"


async def test_update_issue_workspace_from_issue_id(client: Client):
    """update_issue extracts workspace from issue ID prefix."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("update_issue", {
            "issue": "MYPROJ-99",
            "summary": "Updated title",
            "preview": True,
        })

    data = result.data
    assert data["ok"] is True
    assert data["record"]["attributes"]["_workspace?str"] == "MYPROJ"


async def test_update_issue_full_ref(client: Client):
    """update_issue accepts full record ref as issue ID."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("update_issue", {
            "issue": "emodel/ept-issue@PROJ-5",
            "priority": "200_high",
            "preview": True,
        })

    data = result.data
    assert data["ok"] is True
    assert data["record"]["id"] == "emodel/ept-issue@PROJ-5"
    assert data["record"]["attributes"]["_workspace?str"] == "PROJ"
    assert data["record"]["attributes"]["priority?str"] == "200_high"


async def test_update_issue_assignee(client: Client):
    """update_issue sets assignee with emodel/person@ prefix."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("update_issue", {
            "issue": "COREDEV-10",
            "assignee": "developer1",
            "preview": True,
        })

    data = result.data
    assert data["ok"] is True
    assert data["record"]["attributes"]["implementer?str"] == "emodel/person@developer1"


async def test_update_issue_assignee_me(client: Client):
    """update_issue resolves assignee='me' to current username."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    with patch("servers.citeck_mcp.get_username", return_value="current_user"), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("update_issue", {
            "issue": "COREDEV-10",
            "assignee": "me",
            "preview": True,
        })

    data = result.data
    assert data["ok"] is True
    assert data["record"]["attributes"]["implementer?str"] == "emodel/person@current_user"


async def test_update_issue_assignee_me_failure(client: Client):
    """update_issue returns error when 'me' cannot be resolved."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    with patch("servers.citeck_mcp.get_username", side_effect=Exception("no auth")), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("update_issue", {
            "issue": "COREDEV-10",
            "assignee": "me",
            "preview": True,
        })

    data = result.data
    assert data["ok"] is False
    assert "current user" in data["error"].lower()


async def test_update_issue_no_changes(client: Client):
    """update_issue returns error when no attributes to update."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("update_issue", {
            "issue": "COREDEV-10",
            "preview": True,
        })

    data = result.data
    assert data["ok"] is False
    assert "no attributes" in data["error"].lower() or "at least one" in data["error"].lower()


async def test_update_issue_multiple_fields(client: Client):
    """update_issue can update multiple fields at once."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("update_issue", {
            "issue": "COREDEV-42",
            "status": "in-progress",
            "priority": "100_critical",
            "summary": "Updated summary",
            "description": "Updated description",
            "preview": True,
        })

    data = result.data
    assert data["ok"] is True
    attrs = data["record"]["attributes"]
    assert attrs["_state?str"] == "in-progress"
    assert attrs["priority?str"] == "100_critical"
    assert attrs["summary?str"] == "Updated summary"
    assert attrs["description?str"] == "Updated description"
    assert attrs["_workspace?str"] == "COREDEV"


async def test_update_issue_api_error(client: Client):
    """update_issue returns error on API failure."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    with patch("servers.citeck_mcp.lib_records_mutate",
               side_effect=RecordsApiError("HTTP 500 Server Error")), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("update_issue", {
            "issue": "COREDEV-42",
            "status": "done",
            "preview": False,
        })

    data = result.data
    assert data["ok"] is False
    assert "500" in data["error"]
