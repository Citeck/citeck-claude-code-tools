"""Tests for the records_query MCP tool."""

import os
import sys
import tempfile

import pytest
from unittest.mock import patch

from fastmcp import Client

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from servers.citeck_mcp import mcp
from lib.config import save_credentials
from lib.records_api import RecordsApiError, AuthenticationError


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


async def test_records_query_tool_exists(client: Client):
    """records_query tool is registered in the MCP server."""
    tools = await client.list_tools()
    tool_names = [t.name for t in tools]
    assert "records_query" in tool_names


async def test_records_query_by_predicate(client: Client):
    """records_query queries by predicate using records_query from lib."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    mock_response = {
        "records": [
            {"id": "emodel/ept-issue@1", "attributes": {"summary": "Test issue"}}
        ],
        "hasMore": False,
        "totalCount": 1,
    }

    with patch("servers.citeck_mcp.lib_records_query", return_value=mock_response), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("records_query", {
            "source_id": "emodel/ept-issue",
            "query": {"t": "eq", "a": "_status", "v": "open"},
            "attributes": {"summary": "summary?str"},
        })

    data = result.data
    assert data["ok"] is True
    assert len(data["records"]) == 1
    assert data["records"][0]["attributes"]["summary"] == "Test issue"


async def test_records_query_load_by_ids(client: Client):
    """records_query loads specific records when record_ids is provided."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    mock_response = {
        "records": [
            {"id": "emodel/ept-issue@1", "attributes": {"?json": '{"key": "val"}'}}
        ],
    }

    with patch("servers.citeck_mcp.lib_records_load", return_value=mock_response), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("records_query", {
            "record_ids": ["emodel/ept-issue@1"],
            "attributes": {"data": "?json"},
        })

    data = result.data
    assert data["ok"] is True
    assert len(data["records"]) == 1


async def test_records_query_with_pagination(client: Client):
    """records_query passes page parameter correctly."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    mock_response = {"records": [], "hasMore": False, "totalCount": 0}

    with patch("servers.citeck_mcp.lib_records_query", return_value=mock_response) as mock_query, \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("records_query", {
            "source_id": "emodel/ept-issue",
            "attributes": {"id": "id"},
            "page": {"maxItems": 10, "skipCount": 0},
        })

    # Verify page was passed to lib function
    call_kwargs = mock_query.call_args
    assert call_kwargs[1].get("page") == {"maxItems": 10, "skipCount": 0}

    data = result.data
    assert data["ok"] is True


async def test_records_query_with_workspaces(client: Client):
    """records_query passes workspaces parameter correctly."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    mock_response = {"records": [], "hasMore": False, "totalCount": 0}

    with patch("servers.citeck_mcp.lib_records_query", return_value=mock_response) as mock_query, \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        await client.call_tool("records_query", {
            "source_id": "emodel/ept-issue",
            "attributes": {"id": "id"},
            "workspaces": ["COREDEV"],
        })

    call_kwargs = mock_query.call_args
    assert call_kwargs[1].get("workspaces") == ["COREDEV"]


async def test_records_query_auth_error(client: Client):
    """records_query returns error on authentication failure."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    with patch("servers.citeck_mcp.lib_records_query",
               side_effect=AuthenticationError("HTTP 401 Unauthorized", status_code=401)), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("records_query", {
            "source_id": "emodel/ept-issue",
            "attributes": {"id": "id"},
        })

    data = result.data
    assert data["ok"] is False
    assert "401" in data["error"]


async def test_records_query_api_error(client: Client):
    """records_query returns error on API failure."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    with patch("servers.citeck_mcp.lib_records_query",
               side_effect=RecordsApiError("No credentials found")), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("records_query", {
            "source_id": "emodel/ept-issue",
            "attributes": {"id": "id"},
        })

    data = result.data
    assert data["ok"] is False
    assert "No credentials" in data["error"]


async def test_records_query_requires_source_or_ids(client: Client):
    """records_query fails when neither source_id nor record_ids is provided."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("records_query", {
            "attributes": {"id": "id"},
        })

    data = result.data
    assert data["ok"] is False
    assert "source_id" in data["error"] or "record_ids" in data["error"]
