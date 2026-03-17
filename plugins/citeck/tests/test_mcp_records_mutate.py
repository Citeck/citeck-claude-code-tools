"""Tests for the records_mutate MCP tool."""

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


async def test_records_mutate_tool_exists(client: Client):
    """records_mutate tool is registered in the MCP server."""
    tools = await client.list_tools()
    tool_names = [t.name for t in tools]
    assert "records_mutate" in tool_names


async def test_records_mutate_create_record(client: Client):
    """records_mutate creates a new record."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    mock_response = {
        "records": [
            {"id": "emodel/ept-issue@new-uuid", "attributes": {}}
        ],
    }

    with patch("servers.citeck_mcp.lib_records_mutate", return_value=mock_response) as mock_mutate, \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("records_mutate", {
            "records": [
                {
                    "id": "emodel/ept-issue@",
                    "attributes": {
                        "summary?str": "New issue",
                        "_workspace?str": "COREDEV",
                    },
                }
            ],
        })

    # Verify lib function was called with correct args
    call_kwargs = mock_mutate.call_args
    assert call_kwargs[1]["records"][0]["attributes"]["summary?str"] == "New issue"
    assert call_kwargs[1]["version"] == 1

    data = result.data
    assert data["ok"] is True
    assert len(data["records"]) == 1
    assert data["records"][0]["id"] == "emodel/ept-issue@new-uuid"


async def test_records_mutate_update_record(client: Client):
    """records_mutate updates an existing record."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    mock_response = {
        "records": [
            {"id": "emodel/ept-issue@existing-uuid", "attributes": {}}
        ],
    }

    with patch("servers.citeck_mcp.lib_records_mutate", return_value=mock_response) as mock_mutate, \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("records_mutate", {
            "records": [
                {
                    "id": "emodel/ept-issue@existing-uuid",
                    "attributes": {
                        "_state?str": "done",
                        "_workspace?str": "COREDEV",
                    },
                }
            ],
        })

    call_kwargs = mock_mutate.call_args
    assert call_kwargs[1]["records"][0]["id"] == "emodel/ept-issue@existing-uuid"

    data = result.data
    assert data["ok"] is True


async def test_records_mutate_custom_version(client: Client):
    """records_mutate passes version parameter correctly."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    mock_response = {"records": [{"id": "emodel/ept-issue@1", "attributes": {}}]}

    with patch("servers.citeck_mcp.lib_records_mutate", return_value=mock_response) as mock_mutate, \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        await client.call_tool("records_mutate", {
            "records": [{"id": "emodel/ept-issue@1", "attributes": {"summary?str": "test"}}],
            "version": 2,
        })

    call_kwargs = mock_mutate.call_args
    assert call_kwargs[1]["version"] == 2


async def test_records_mutate_empty_records(client: Client):
    """records_mutate fails when records list is empty."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("records_mutate", {
            "records": [],
        })

    data = result.data
    assert data["ok"] is False
    assert "records" in data["error"].lower()


async def test_records_mutate_auth_error(client: Client):
    """records_mutate returns error on authentication failure."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    with patch("servers.citeck_mcp.lib_records_mutate",
               side_effect=AuthenticationError("HTTP 401 Unauthorized", status_code=401)), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("records_mutate", {
            "records": [{"id": "emodel/ept-issue@1", "attributes": {"summary?str": "test"}}],
        })

    data = result.data
    assert data["ok"] is False
    assert "401" in data["error"]


async def test_records_mutate_api_error(client: Client):
    """records_mutate returns error on API failure."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    with patch("servers.citeck_mcp.lib_records_mutate",
               side_effect=RecordsApiError("Server error: HTTP 500")), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("records_mutate", {
            "records": [{"id": "emodel/ept-issue@1", "attributes": {"summary?str": "test"}}],
        })

    data = result.data
    assert data["ok"] is False
    assert "500" in data["error"]
