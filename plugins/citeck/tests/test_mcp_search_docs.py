"""Tests for the MCP tools search_docs and set_docs_profile."""

import os
import shutil
import sys
import tempfile

import pytest
from unittest.mock import patch
from fastmcp import Client

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from servers.citeck_mcp import mcp
from lib import config, rag_api


@pytest.fixture
async def client():
    async with Client(mcp) as c:
        yield c


@pytest.fixture
def config_dir():
    d = tempfile.mkdtemp()
    _setup_profiles(d)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _setup_profiles(config_dir):
    config.save_credentials(
        profile="local",
        url="http://localhost",
        username="admin",
        password="admin",
        config_dir=config_dir,
    )
    config.save_credentials(
        profile="prod",
        url="https://citeck.example.com",
        username="u",
        password="p",
        config_dir=config_dir,
    )


async def test_search_docs_tool_registered(client: Client):
    tools = await client.list_tools()
    names = [t.name for t in tools]
    assert "search_docs" in names
    assert "set_docs_profile" in names


async def test_search_docs_empty_question(client: Client, config_dir: str):
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("search_docs", {"question": "   "})
    assert result.data["ok"] is False
    assert "empty" in result.data["error"].lower()


async def test_search_docs_success_trims_metadata(client: Client, config_dir: str):
    raw = [{
        "documentId": "chunk-1",
        "sourceId": "citeck-docs",
        "content": "Workspaces group records.",
        "score": 0.83,
        "metadata": {
            "file_path": "docs/workspaces/overview.md",
            "file_type": "md",
            "source_id": "citeck-docs",
            "permissions_authorities": ["GROUP_all"],
            "ecos_type": "DOCUMENT",
        },
    }]
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.lib_search_docs", return_value=raw) as mock_search:
        result = await client.call_tool("search_docs", {"question": "what is a workspace?"})

    assert result.data["ok"] is True
    assert result.data["count"] == 1
    hit = result.data["results"][0]
    assert hit == {
        "score": 0.83,
        "file_path": "docs/workspaces/overview.md",
        "file_type": "md",
        "source_id": "citeck-docs",
        "content": "Workspaces group records.",
    }
    # permissions_authorities and ecos_type must be stripped
    assert "permissions_authorities" not in hit
    assert "ecos_type" not in hit
    # no url when base_doc_url is absent
    assert "url" not in hit
    # server surfaced for the user
    assert result.data["server"] == "http://localhost"
    assert result.data["profile"] == "local"
    # resolved profile must be forwarded to lib_search_docs
    _, kwargs = mock_search.call_args
    assert kwargs["profile"] == "local"


async def test_search_docs_routes_via_docs_profile(client: Client, config_dir: str):
    config.set_docs_profile("prod", config_dir)
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.lib_search_docs", return_value=[]) as _m:
        result = await client.call_tool("search_docs", {"question": "q"})
    assert result.data["ok"] is True
    assert result.data["profile"] == "prod"
    assert result.data["server"] == "https://citeck.example.com"


async def test_search_docs_truncates_long_content(client: Client, config_dir: str):
    long_content = "x" * 5000
    raw = [{
        "documentId": "c",
        "sourceId": "citeck-docs",
        "content": long_content,
        "score": 0.5,
        "metadata": {"file_path": "f.md", "file_type": "md"},
    }]
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.lib_search_docs", return_value=raw):
        result = await client.call_tool("search_docs", {"question": "q"})
    content = result.data["results"][0]["content"]
    assert len(content) <= 2001  # 2000 chars + trailing ellipsis
    assert content.endswith("…")


async def test_search_docs_propagates_profile_override(client: Client, config_dir: str):
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.lib_search_docs", return_value=[]) as mock_search:
        await client.call_tool("search_docs", {"question": "q", "profile": "prod"})
    _, kwargs = mock_search.call_args
    assert kwargs["profile"] == "prod"


async def test_search_docs_rag_api_error(client: Client, config_dir: str):
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.lib_search_docs",
               side_effect=rag_api.RagApiError("boom")):
        result = await client.call_tool("search_docs", {"question": "q"})
    assert result.data["ok"] is False
    assert "boom" in result.data["error"]


async def test_set_docs_profile_success(client: Client, config_dir: str):
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("set_docs_profile", {"profile": "prod"})
    assert result.data["ok"] is True
    assert result.data["docs_profile"] == "prod"
    assert result.data["server"] == "https://citeck.example.com"
    assert config.get_docs_profile(config_dir) == "prod"


async def test_set_docs_profile_clears_when_empty(client: Client, config_dir: str):
    config.set_docs_profile("prod", config_dir)
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("set_docs_profile", {"profile": ""})
    assert result.data["ok"] is True
    assert result.data.get("cleared") is True
    assert config.get_docs_profile(config_dir) is None


async def test_set_docs_profile_rejects_unknown(client: Client, config_dir: str):
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("set_docs_profile", {"profile": "ghost"})
    assert result.data["ok"] is False
    assert "ghost" in result.data["error"]


async def test_search_docs_builds_readthedocs_url(client: Client, config_dir: str):
    raw = [{
        "documentId": "c",
        "sourceId": "citeck-docs",
        "content": "Records API overview.",
        "score": 0.9,
        "metadata": {
            "file_path": "docs/general/Data_API/ECOS_Records.rst",
            "file_type": "rst",
            "base_doc_url": "https://citeck-ecos.readthedocs.io/ru/stable",
            "docs_root_path": "docs",
            "url_extension": ".html",
        },
    }]
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.lib_search_docs", return_value=raw):
        result = await client.call_tool("search_docs", {"question": "q"})
    hit = result.data["results"][0]
    assert hit["url"] == (
        "https://citeck-ecos.readthedocs.io/ru/stable/general/Data_API/ECOS_Records.html"
    )
    # original path is retained
    assert hit["file_path"] == "docs/general/Data_API/ECOS_Records.rst"


async def test_search_docs_url_without_root_or_extension(client: Client, config_dir: str):
    # No docs_root_path and empty url_extension — just prepend base.
    raw = [{
        "documentId": "c",
        "sourceId": "citeck-docs",
        "content": "x",
        "score": 0.7,
        "metadata": {
            "file_path": "intro/overview.md",
            "base_doc_url": "https://docs.example.com/",
            "url_extension": "",
        },
    }]
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.lib_search_docs", return_value=raw):
        result = await client.call_tool("search_docs", {"question": "q"})
    assert result.data["results"][0]["url"] == "https://docs.example.com/intro/overview"


async def test_search_docs_url_missing_when_no_base(client: Client, config_dir: str):
    raw = [{
        "documentId": "c",
        "sourceId": "citeck-docs",
        "content": "x",
        "score": 0.7,
        "metadata": {
            "file_path": "docs/a.md",
            "docs_root_path": "docs",
            "url_extension": ".html",
        },
    }]
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.lib_search_docs", return_value=raw):
        result = await client.call_tool("search_docs", {"question": "q"})
    assert "url" not in result.data["results"][0]
