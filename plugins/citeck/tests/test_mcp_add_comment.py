"""Tests for the add_comment MCP tool."""

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


async def test_add_comment_tool_exists(client: Client):
    """add_comment tool is registered in the MCP server."""
    tools = await client.list_tools()
    tool_names = [t.name for t in tools]
    assert "add_comment" in tool_names


async def test_add_comment_preview_mode(client: Client):
    """preview_comment returns a preview without posting."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("preview_comment", {
            "issue": "COREDEV-42",
            "text": "<p>Test comment</p>",
        })

    data = result.data
    assert data["ok"] is True
    assert data["preview"] is True
    record = data["record"]
    assert record["id"] == "emodel/comment@"
    attrs = record["attributes"]
    assert attrs["text?str"] == "<p>Test comment</p>"
    assert attrs["record?str"] == "emodel/ept-issue@COREDEV-42"
    assert attrs["_workspace?str"] == "COREDEV"


async def test_add_comment_actual_post(client: Client):
    """add_comment performs the mutation and returns id+link."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    mock_mutate_response = {
        "records": [
            {"id": "emodel/comment@new-comment-uuid"},
        ],
    }

    with patch("servers.citeck_mcp.lib_records_mutate", return_value=mock_mutate_response) as mock_mutate, \
         patch("servers.citeck_mcp.get_credentials", return_value={"url": "http://localhost"}), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("add_comment", {
            "issue": "COREDEV-42",
            "text": "Done",
        })

    data = result.data
    assert data["ok"] is True
    assert data["id"] == "emodel/comment@new-comment-uuid"
    assert data["issue"] == "emodel/ept-issue@COREDEV-42"
    assert "link" in data
    assert "COREDEV-42" in data["link"]

    # Verify mutate was called with proper attributes
    call_args = mock_mutate.call_args
    records = call_args[1]["records"]
    assert len(records) == 1
    assert records[0]["id"] == "emodel/comment@"
    attrs = records[0]["attributes"]
    assert attrs["text?str"] == "Done"
    assert attrs["record?str"] == "emodel/ept-issue@COREDEV-42"
    assert attrs["_workspace?str"] == "COREDEV"


async def test_add_comment_empty_text(client: Client):
    """add_comment returns error when text is empty or whitespace."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("preview_comment", {
            "issue": "COREDEV-42",
            "text": "   ",
        })

    data = result.data
    assert data["ok"] is False
    assert "text" in data["error"].lower()


async def test_add_comment_full_ref_issue_preserved(client: Client):
    """add_comment accepts a full record ref as issue and preserves it."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("preview_comment", {
            "issue": "emodel/ept-issue@MYPROJ-7",
            "text": "Note",
        })

    data = result.data
    assert data["ok"] is True
    attrs = data["record"]["attributes"]
    assert attrs["record?str"] == "emodel/ept-issue@MYPROJ-7"
    assert attrs["_workspace?str"] == "MYPROJ"


async def test_add_comment_api_error(client: Client):
    """add_comment returns error on API failure."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    with patch("servers.citeck_mcp.lib_records_mutate",
               side_effect=RecordsApiError("HTTP 500 Server Error")), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("add_comment", {
            "issue": "COREDEV-42",
            "text": "Hi",
        })

    data = result.data
    assert data["ok"] is False
    assert "500" in data["error"]
