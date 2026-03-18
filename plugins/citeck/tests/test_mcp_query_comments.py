"""Tests for the query_comments MCP tool."""

import os
import sys
import tempfile

import pytest
from unittest.mock import patch

from fastmcp import Client

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from servers.citeck_mcp import mcp, _strip_html, _format_comments, _extract_image_urls
from lib.config import save_credentials
from lib.records_api import RecordsApiError


@pytest.fixture
async def client():
    async with Client(mcp) as c:
        yield c


def _setup_credentials(config_dir):
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


# -- Unit tests for _strip_html --


class TestStripHtml:
    def test_plain_text(self):
        assert _strip_html("hello world") == "hello world"

    def test_removes_tags(self):
        assert _strip_html("<p>Hello <b>world</b></p>") == "Hello world"

    def test_decodes_entities(self):
        assert _strip_html("&lt;tag&gt; &amp; text") == "<tag> & text"

    def test_empty(self):
        assert _strip_html("") == ""

    def test_none(self):
        assert _strip_html(None) == ""

    def test_collapses_whitespace(self):
        assert _strip_html("<p>line1</p>  <p>line2</p>") == "line1 line2"

    def test_nested_tags(self):
        html = '<ol><li><span>Item 1</span></li><li><span>Item 2</span></li></ol>'
        result = _strip_html(html)
        assert "Item 1" in result
        assert "Item 2" in result


# -- Unit tests for _extract_image_urls --


class TestExtractImageUrls:
    def test_no_images(self):
        assert _extract_image_urls("<p>Hello world</p>") == []

    def test_single_absolute_img(self):
        html = '<img src="https://host/img.png">'
        assert _extract_image_urls(html) == ["https://host/img.png"]

    def test_relative_img_with_base_url(self):
        html = '<img src="/gateway/api/content?ref=abc">'
        result = _extract_image_urls(html, base_url="https://citeck.example.com")
        assert result == ["https://citeck.example.com/gateway/api/content?ref=abc"]

    def test_relative_img_without_base_url(self):
        html = '<img src="/gateway/img.png">'
        result = _extract_image_urls(html)
        assert result == ["/gateway/img.png"]

    def test_deduplicates(self):
        html = '<img src="/img.png"><img src="/img.png">'
        result = _extract_image_urls(html, base_url="https://host")
        assert result == ["https://host/img.png"]

    def test_empty_html(self):
        assert _extract_image_urls("") == []

    def test_none_html(self):
        assert _extract_image_urls(None) == []

    def test_multiple_images(self):
        html = '<img src="/a.png"><p>text</p><img src="/b.jpg">'
        result = _extract_image_urls(html, base_url="https://host")
        assert result == ["https://host/a.png", "https://host/b.jpg"]


# -- Unit tests for _format_comments --


class TestFormatComments:
    def test_basic(self):
        raw = [
            {
                "id": "emodel/comment@uuid1",
                "attributes": {
                    "text": "<p>Hello <b>world</b></p>",
                    "created": "2026-03-18T10:00:00Z",
                    "modified": "2026-03-18T10:01:00Z",
                    "creator": {
                        "authorityName": "admin",
                        "userName": "admin",
                        "displayName": "Admin User",
                        "firstName": "Admin",
                        "lastName": "User",
                        "avatarUrl": "/avatar.png",
                    },
                    "modifier": {
                        "authorityName": "admin",
                        "userName": "admin",
                        "displayName": "Admin User",
                        "firstName": "Admin",
                        "lastName": "User",
                    },
                    "canEdit": True,
                    "edited": False,
                    "tags": [{"type": "label", "name": "important"}],
                },
            }
        ]
        result = _format_comments(raw)
        assert len(result) == 1
        c = result[0]
        assert c["id"] == "emodel/comment@uuid1"
        assert c["text"] == "Hello world"
        assert c["textHtml"] == "<p>Hello <b>world</b></p>"
        assert c["imageUrls"] == []
        assert c["creator"]["username"] == "admin"
        assert c["creator"]["displayName"] == "Admin User"
        assert c["creator"]["avatarUrl"] == "/avatar.png"
        assert c["canEdit"] is True
        assert c["edited"] is False
        assert c["tags"] == [{"type": "label", "name": "important"}]

    def test_empty_text(self):
        raw = [{"id": "emodel/comment@uuid2", "attributes": {"text": None}}]
        result = _format_comments(raw)
        assert result[0]["text"] == ""
        assert result[0]["textHtml"] == ""
        assert result[0]["imageUrls"] == []

    def test_scalar_creator(self):
        raw = [{"id": "emodel/comment@uuid3", "attributes": {"creator": "admin"}}]
        result = _format_comments(raw)
        assert result[0]["creator"]["displayName"] == "admin"

    def test_image_urls_extracted(self):
        raw = [{
            "id": "emodel/comment@uuid4",
            "attributes": {
                "text": '<p>See: <img src="/gateway/content?ref=abc"></p>',
            },
        }]
        result = _format_comments(raw, base_url="http://localhost")
        assert result[0]["imageUrls"] == ["http://localhost/gateway/content?ref=abc"]

    def test_no_base_url_returns_raw_src(self):
        raw = [{
            "id": "emodel/comment@uuid5",
            "attributes": {
                "text": '<img src="/img.png">',
            },
        }]
        result = _format_comments(raw)
        assert result[0]["imageUrls"] == ["/img.png"]


# -- MCP tool tests --


@pytest.mark.anyio
async def test_query_comments_tool_exists(client: Client):
    tools = await client.list_tools()
    assert "query_comments" in [t.name for t in tools]


@pytest.mark.anyio
async def test_query_comments_basic(client: Client):
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    mock_response = {
        "records": [
            {
                "id": "emodel/comment@uuid1",
                "attributes": {
                    "text": "<p>Fix this <b>ASAP</b></p>",
                    "created": "2026-03-18T10:00:00Z",
                    "modified": "2026-03-18T10:00:00Z",
                    "creator": {
                        "userName": "dev1",
                        "displayName": "Developer One",
                        "firstName": "Developer",
                        "lastName": "One",
                        "avatarUrl": "",
                    },
                    "modifier": {
                        "userName": "dev1",
                        "displayName": "Developer One",
                        "firstName": "Developer",
                        "lastName": "One",
                    },
                    "canEdit": False,
                    "edited": False,
                    "tags": [],
                },
            }
        ],
        "totalCount": 1,
        "hasMore": False,
    }

    with patch("servers.citeck_mcp.lib_records_query", return_value=mock_response) as mock_query, \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("query_comments", {
            "record_ref": "emodel/ept-issue@COREDEV-3703",
        })

    data = result.data
    assert data["ok"] is True
    assert data["count"] == 1
    assert data["totalCount"] == 1
    assert data["hasMore"] is False

    comment = data["comments"][0]
    assert comment["text"] == "Fix this ASAP"
    assert comment["textHtml"] == "<p>Fix this <b>ASAP</b></p>"
    assert comment["imageUrls"] == []
    assert comment["creator"]["username"] == "dev1"

    call_kwargs = mock_query.call_args[1]
    assert call_kwargs["source_id"] == "emodel/comment"
    assert call_kwargs["language"] == "predicate"
    assert call_kwargs["query"] == {"t": "eq", "a": "record", "v": "emodel/ept-issue@COREDEV-3703"}
    assert call_kwargs["sort_by"] == [{"attribute": "_created", "ascending": False}]
    assert call_kwargs["page"] == {"skipCount": 0, "maxItems": 50}


@pytest.mark.anyio
async def test_query_comments_with_images(client: Client):
    """Comments with images return resolved imageUrls."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    mock_response = {
        "records": [
            {
                "id": "emodel/comment@uuid1",
                "attributes": {
                    "text": '<p>Bug: <img src="/gateway/content?ref=att%40abc&amp;att=content"></p>',
                    "created": "2026-03-18T10:00:00Z",
                },
            }
        ],
        "totalCount": 1,
        "hasMore": False,
    }

    with patch("servers.citeck_mcp.lib_records_query", return_value=mock_response), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("query_comments", {
            "record_ref": "emodel/ept-issue@COREDEV-1",
        })

    data = result.data
    assert data["ok"] is True
    comment = data["comments"][0]
    assert len(comment["imageUrls"]) == 1
    assert comment["imageUrls"][0].startswith("http://localhost/")


@pytest.mark.anyio
async def test_query_comments_empty_record_ref(client: Client):
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("query_comments", {"record_ref": ""})

    data = result.data
    assert data["ok"] is False
    assert "record_ref" in data["error"]


@pytest.mark.anyio
async def test_query_comments_pagination(client: Client):
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    mock_response = {"records": [], "totalCount": 0, "hasMore": False}

    with patch("servers.citeck_mcp.lib_records_query", return_value=mock_response) as mock_query, \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        await client.call_tool("query_comments", {
            "record_ref": "emodel/ept-issue@COREDEV-1",
            "limit": 10,
            "skip_count": 20,
        })

    call_kwargs = mock_query.call_args[1]
    assert call_kwargs["page"] == {"skipCount": 20, "maxItems": 10}


@pytest.mark.anyio
async def test_query_comments_api_error(client: Client):
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    with patch("servers.citeck_mcp.lib_records_query",
               side_effect=RecordsApiError("HTTP 500")), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("query_comments", {
            "record_ref": "emodel/ept-issue@COREDEV-1",
        })

    data = result.data
    assert data["ok"] is False
    assert "500" in data["error"]


@pytest.mark.anyio
async def test_query_comments_empty_result(client: Client):
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    mock_response = {"records": [], "totalCount": 0, "hasMore": False}

    with patch("servers.citeck_mcp.lib_records_query", return_value=mock_response), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("query_comments", {
            "record_ref": "emodel/ept-issue@COREDEV-9999",
        })

    data = result.data
    assert data["ok"] is True
    assert data["count"] == 0
    assert data["comments"] == []
