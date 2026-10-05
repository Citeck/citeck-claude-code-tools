"""Tests that tracker tools route via ept_profile and records tools via records_profile."""

import os
import shutil
import sys
import tempfile

import pytest
from unittest.mock import patch
from fastmcp import Client

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from servers.citeck_mcp import mcp
from lib import config


@pytest.fixture
async def client():
    async with Client(mcp) as c:
        yield c


@pytest.fixture
def config_dir():
    d = tempfile.mkdtemp()
    config.save_credentials(
        profile="local",
        url="http://localhost",
        username="admin",
        password="admin",
        auth_method="oidc",
        config_dir=d,
    )
    config.save_credentials(
        profile="prod",
        url="https://prod.example.com",
        username="u",
        password="p",
        auth_method="oidc",
        config_dir=d,
    )
    # active = "local" (first profile saved)
    yield d
    shutil.rmtree(d, ignore_errors=True)


# --- records_query routing ---

@pytest.mark.parametrize("assignee", ["other.user", "configured.user"])
async def test_preview_and_create_keep_explicit_profile_and_issue_fields(client, config_dir, assignee):
    params = {"type": "task", "summary": "Adapt plugin", "project": "PROJECT",
              "profile": "prod", "assignee": assignee, "fix_in_version": ["release-id"]}
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp._resolve_project_info", return_value=("emodel/project@p", "workspace")), \
         patch("servers.citeck_mcp._resolve_ref_labels", return_value={}), \
         patch("servers.citeck_mcp.get_username", return_value="reporter"), \
         patch("servers.citeck_mcp.lib_records_mutate", return_value={
             "records": [{"id": "emodel/ept-issue@id", "attributes": {}}]}) as mutate:
        preview = (await client.call_tool("preview_issue", params)).data
        assert preview["ok"] is True
        assert preview["profile"] == "prod"
        mutate.assert_not_called()
        # Another session changes both defaults after the preview.
        config.set_ept_profile("local", config_dir)
        config.set_active_profile("local", config_dir)
        created = (await client.call_tool("create_issue", {**params, "expected_server": preview["server"]})).data
        assert created["ok"] is True
        assert mutate.call_args.kwargs["profile"] == "prod"
        assert mutate.call_args.kwargs["expected_server"] == preview["server"]
        record = mutate.call_args.kwargs["records"][0]
        assert record == preview["record"]
        assert record["attributes"]["implementer?str"] == f"emodel/person@{assignee}"
        assert record["attributes"]["fixInVersion?assoc"] == ["emodel/ecos-release-type@release-id"]


async def test_deleted_explicit_profile_never_falls_back_on_create(client, config_dir):
    data = config._read_config(config_dir)
    del data["profiles"]["prod"]
    config._write_config(data, config_dir)
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.lib_records_mutate") as mutate:
        result = (await client.call_tool("create_issue", {
            "type": "task", "summary": "Adapt plugin", "project": "PROJECT", "profile": "prod"
        })).data
        assert result["ok"] is False
        mutate.assert_not_called()

async def test_records_query_uses_records_profile(client: Client, config_dir: str):
    config.set_records_profile("prod", config_dir)
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.lib_records_query", return_value={"records": []}) as mock_q:
        await client.call_tool("records_query", {"source_id": "emodel/ept-issue"})
    _, kwargs = mock_q.call_args
    assert kwargs["profile"] == "prod"


async def test_records_query_falls_back_to_active(client: Client, config_dir: str):
    # No records_profile set — should use active ("local")
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.lib_records_query", return_value={"records": []}) as mock_q:
        await client.call_tool("records_query", {"source_id": "emodel/ept-issue"})
    _, kwargs = mock_q.call_args
    assert kwargs["profile"] == "local"


async def test_records_query_per_call_override_wins(client: Client, config_dir: str):
    config.set_records_profile("local", config_dir)
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.lib_records_query", return_value={"records": []}) as mock_q:
        await client.call_tool(
            "records_query",
            {"source_id": "emodel/ept-issue", "profile": "prod"},
        )
    _, kwargs = mock_q.call_args
    assert kwargs["profile"] == "prod"


async def test_records_query_load_by_ids_uses_records_profile(client: Client, config_dir: str):
    config.set_records_profile("prod", config_dir)
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.lib_records_load", return_value={"records": []}) as mock_load:
        await client.call_tool("records_query", {"record_ids": ["emodel/ept-issue@COREDEV-1"]})
    _, kwargs = mock_load.call_args
    assert kwargs["profile"] == "prod"


# --- records_mutate routing ---

async def test_records_mutate_uses_records_profile(client: Client, config_dir: str):
    config.set_records_profile("prod", config_dir)
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.lib_records_mutate", return_value={"records": []}) as mock_m:
        result = await client.call_tool(
            "records_mutate",
            {"records": [{"id": "x@", "attributes": {"a?str": "v"}}]},
        )
    assert result.data["ok"] is True, result.data
    _, kwargs = mock_m.call_args
    assert kwargs["profile"] == "prod"
    assert result.data["profile"] == "prod"
    assert result.data["server"] == "https://prod.example.com"


# --- search_issues routing (representative ept tool) ---

async def test_search_issues_uses_ept_profile(client: Client, config_dir: str):
    config.set_ept_profile("prod", config_dir)
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.lib_records_query", return_value={"records": []}) as mock_q:
        await client.call_tool("search_issues", {"project": "COREDEV"})
    _, kwargs = mock_q.call_args
    assert kwargs["profile"] == "prod"


async def test_search_issues_falls_back_to_active(client: Client, config_dir: str):
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.lib_records_query", return_value={"records": []}) as mock_q:
        await client.call_tool("search_issues", {"project": "COREDEV"})
    _, kwargs = mock_q.call_args
    assert kwargs["profile"] == "local"


async def test_search_issues_per_call_override_wins(client: Client, config_dir: str):
    config.set_ept_profile("local", config_dir)
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.lib_records_query", return_value={"records": []}) as mock_q:
        await client.call_tool(
            "search_issues",
            {"project": "COREDEV", "profile": "prod"},
        )
    _, kwargs = mock_q.call_args
    assert kwargs["profile"] == "prod"


# --- ept and records are independent ---

async def test_ept_and_records_profiles_are_independent(client: Client, config_dir: str):
    """Setting ept_profile must not affect records_query routing, and vice versa."""
    config.set_ept_profile("prod", config_dir)
    # records_profile unset → records_query should use active ("local"), not ept_profile
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.lib_records_query", return_value={"records": []}) as mock_q:
        await client.call_tool("records_query", {"source_id": "emodel/ept-issue"})
    _, kwargs = mock_q.call_args
    assert kwargs["profile"] == "local"


# --- missing-profile error ---

async def test_records_query_errors_when_records_profile_missing(client: Client, config_dir: str):
    """records_profile referencing a non-configured profile must surface a clear error."""
    config.set_records_profile("local", config_dir)
    # Now remove "local" from profiles by rewriting the file.
    import json
    path = os.path.join(config_dir, "credentials.json")
    with open(path) as f:
        data = json.load(f)
    del data["profiles"]["local"]
    data["active_profile"] = "prod"
    with open(path, "w") as f:
        json.dump(data, f)

    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("records_query", {"source_id": "emodel/ept-issue"})
    assert result.data["ok"] is False
    assert "records_profile" in result.data["error"]


async def test_changed_confirmed_server_rejects_issue_creation(client, config_dir):
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp._resolve_project_info", return_value=("emodel/project@p", "workspace")), \
         patch("servers.citeck_mcp.get_username", return_value="reporter"), \
         patch("servers.citeck_mcp.lib_records_mutate") as mutate:
        result = (await client.call_tool("create_issue", {
            "type": "task", "summary": "Adapt plugin", "project": "PROJECT", "profile": "prod",
            "expected_server": "https://previous.example.com"
        })).data
        assert result["ok"] is False
        assert "server changed" in result["error"]
        mutate.assert_not_called()
