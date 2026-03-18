"""Tests for the download_attachment MCP tool."""

import os
import sys
import tempfile
import urllib.error

import pytest
from unittest.mock import patch, MagicMock

from fastmcp import Client

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from servers.citeck_mcp import mcp
from lib.config import save_credentials
from lib.auth import AuthError


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


def _mock_urlopen_response(data: bytes, content_type: str = "image/png"):
    """Create a mock urllib response with given data and content type."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = data
    mock_resp.headers = {"Content-Type": content_type}
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


@pytest.mark.anyio
async def test_download_attachment_tool_exists(client: Client):
    tools = await client.list_tools()
    assert "download_attachment" in [t.name for t in tools]


@pytest.mark.anyio
async def test_download_success(client: Client):
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    image_data = b"\x89PNG\r\n\x1a\nfake_image_data"
    mock_resp = _mock_urlopen_response(image_data, "image/png")

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.get_auth_header", return_value="Basic dGVzdA=="), \
         patch("servers.citeck_mcp.urllib.request.urlopen", return_value=mock_resp):
        result = await client.call_tool("download_attachment", {
            "url": "/gateway/content?ref=abc",
        })

    data = result.data
    assert data["ok"] is True
    assert data["path"].endswith(".png")
    assert data["content_type"] == "image/png"
    assert data["size"] == len(image_data)
    assert os.path.exists(data["path"])

    with open(data["path"], "rb") as f:
        assert f.read() == image_data

    os.unlink(data["path"])


@pytest.mark.anyio
async def test_download_relative_url_resolved(client: Client):
    """Relative URL is resolved against credentials base URL."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    mock_resp = _mock_urlopen_response(b"data", "application/octet-stream")

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.get_auth_header", return_value="Basic dGVzdA=="), \
         patch("servers.citeck_mcp.urllib.request.urlopen", return_value=mock_resp) as mock_open:
        await client.call_tool("download_attachment", {
            "url": "/gateway/api/content?ref=att%40abc",
        })

    # Check the URL passed to urlopen
    req = mock_open.call_args[0][0]
    assert req.full_url == "http://localhost/gateway/api/content?ref=att%40abc"

    # Cleanup temp file
    path = (await client.call_tool("download_attachment", {"url": "/x"})).data.get("path")
    if path and os.path.exists(path):
        os.unlink(path)


@pytest.mark.anyio
async def test_download_absolute_url_kept(client: Client):
    """Absolute URL is used as-is."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    mock_resp = _mock_urlopen_response(b"data", "image/jpeg")

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.get_auth_header", return_value="Basic dGVzdA=="), \
         patch("servers.citeck_mcp.urllib.request.urlopen", return_value=mock_resp) as mock_open:
        result = await client.call_tool("download_attachment", {
            "url": "https://other-host.com/file.jpg",
        })

    req = mock_open.call_args[0][0]
    assert req.full_url == "https://other-host.com/file.jpg"
    assert result.data["ok"] is True

    if os.path.exists(result.data["path"]):
        os.unlink(result.data["path"])


@pytest.mark.anyio
async def test_download_empty_url(client: Client):
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("download_attachment", {"url": ""})

    data = result.data
    assert data["ok"] is False
    assert "url" in data["error"]


@pytest.mark.anyio
async def test_download_no_credentials(client: Client):
    config_dir = tempfile.mkdtemp()

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("download_attachment", {
            "url": "/gateway/content?ref=abc",
        })

    data = result.data
    assert data["ok"] is False
    assert "No credentials" in data["error"]


@pytest.mark.anyio
async def test_download_http_404(client: Client):
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.get_auth_header", return_value="Basic dGVzdA=="), \
         patch("servers.citeck_mcp.urllib.request.urlopen",
               side_effect=urllib.error.HTTPError(None, 404, "Not Found", {}, None)):
        result = await client.call_tool("download_attachment", {
            "url": "/gateway/content?ref=missing",
        })

    data = result.data
    assert data["ok"] is False
    assert "404" in data["error"]


@pytest.mark.anyio
async def test_download_connection_error(client: Client):
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.get_auth_header", return_value="Basic dGVzdA=="), \
         patch("servers.citeck_mcp.urllib.request.urlopen",
               side_effect=urllib.error.URLError("Connection refused")):
        result = await client.call_tool("download_attachment", {
            "url": "/gateway/content?ref=abc",
        })

    data = result.data
    assert data["ok"] is False
    assert "Connection error" in data["error"]


@pytest.mark.anyio
async def test_download_auth_error(client: Client):
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.get_auth_header",
               side_effect=AuthError("Token expired")):
        result = await client.call_tool("download_attachment", {
            "url": "/gateway/content?ref=abc",
        })

    data = result.data
    assert data["ok"] is False
    assert "Token expired" in data["error"]


@pytest.mark.anyio
async def test_download_jpeg_extension(client: Client):
    """JPEG content type gets .jpg extension, not .jpe."""
    config_dir = tempfile.mkdtemp()
    _setup_credentials(config_dir)

    mock_resp = _mock_urlopen_response(b"jpeg_data", "image/jpeg")

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.get_auth_header", return_value="Basic dGVzdA=="), \
         patch("servers.citeck_mcp.urllib.request.urlopen", return_value=mock_resp):
        result = await client.call_tool("download_attachment", {
            "url": "/gateway/content?ref=photo",
        })

    data = result.data
    assert data["ok"] is True
    assert data["path"].endswith(".jpg")
    assert data["content_type"] == "image/jpeg"

    os.unlink(data["path"])
