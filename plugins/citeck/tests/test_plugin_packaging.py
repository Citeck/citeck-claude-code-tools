"""Validate both clients' package entry points and a relocated stdio server."""

import json
import shutil
import sys
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport


PLUGIN = Path(__file__).resolve().parents[1]
REPO = PLUGIN.parents[1]
sys.path.insert(0, str(PLUGIN))
from lib import config as credentials_config


def test_manifests_and_marketplaces():
    manifests = [json.loads((PLUGIN / folder / "plugin.json").read_text())
                 for folder in (".claude-plugin", ".codex-plugin")]
    assert {item["name"] for item in manifests} == {"citeck"}
    assert len({item["version"] for item in manifests}) == 1
    for manifest in manifests:
        for key in ("skills", "mcpServers"):
            value = manifest[key]
            assert value.startswith("./") and ".." not in Path(value).parts
            assert (PLUGIN / value).exists()
        skills = list((PLUGIN / manifest["skills"]).glob("*/SKILL.md"))
        assert len(skills) == 5
        servers = json.loads((PLUGIN / manifest["mcpServers"]).read_text())["mcpServers"]
        assert set(servers) == {"citeck"}
    for folder in (".claude-plugin", ".agents/plugins"):
        catalog = json.loads((REPO / folder / "marketplace.json").read_text())
        entry, = catalog["plugins"]
        source = entry["source"]
        path = source if isinstance(source, str) else source["path"]
        assert (REPO / path).resolve() == PLUGIN


@pytest.mark.asyncio
async def test_relocated_server_and_resources(tmp_path):
    installed = tmp_path / "installed plugin with spaces"
    shutil.copytree(PLUGIN, installed, ignore=shutil.ignore_patterns(
        ".venv", "__pycache__", ".pytest_cache"))
    config = json.loads((installed / ".mcp.codex.json").read_text())["mcpServers"]["citeck"]
    assert (installed / config["cwd"]).resolve() == installed
    server_path = installed / config["args"][-1]
    assert server_path.is_file()
    assert (installed / "skills/citeck-changes-to-task/../_shared/task-description-guide.md").is_file()
    launcher = (f"import sys, runpy; sys.path.insert(0, {str(installed)!r}); "
                f"from lib import config; config.DEFAULT_CONFIG_DIR = {str(tmp_path / 'credentials')!r}; "
                f"runpy.run_path({str(server_path)!r}, run_name='__main__')")
    transport = StdioTransport(command=sys.executable, args=["-c", launcher], cwd=str(tmp_path))
    async with Client(transport) as client:
        names = {tool.name for tool in await client.list_tools()}
        assert {"ping", "search_docs", "preview_issue", "create_issue", "reauthenticate"} <= names
        assert (await client.call_tool("ping", {})).data == {"ok": True}
        profiles = (await client.call_tool("list_profiles", {})).data
        assert profiles["ok"] is True
        assert profiles["profiles"] == []

        credentials_config.save_credentials(
            "fixture", "http://fixture.invalid", username="test", password="test",
            auth_method="basic", config_dir=str(tmp_path / "credentials"))
        refreshed = (await client.call_tool("list_profiles", {})).data
        assert refreshed["active"] == "fixture"
        assert refreshed["profiles"][0]["url"] == "http://fixture.invalid"
        assert "password" not in refreshed["profiles"][0]
        assert ((tmp_path / "credentials/credentials.json").stat().st_mode & 0o777) == 0o600
        assert ((tmp_path / "credentials").stat().st_mode & 0o777) == 0o700
