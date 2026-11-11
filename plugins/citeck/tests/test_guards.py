"""Run-time guards: allowed servers and generation mode."""

import os
import sys
import tempfile
from unittest.mock import patch

import pytest
from fastmcp import Client

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib import guards, records_api
from lib.config import save_credentials
from servers.citeck_mcp import mcp


@pytest.fixture
async def client():
    async with Client(mcp) as c:
        yield c


def _credentials(url="http://localhost"):
    config_dir = tempfile.mkdtemp()
    save_credentials(profile="default", url=url, username="admin", password="admin",
                     auth_method="basic", config_dir=config_dir)
    return config_dir


def test_allowed_servers_unset_allows_any(monkeypatch):
    monkeypatch.delenv(guards.ALLOWED_SERVERS_ENV, raising=False)
    assert guards.allowed_servers() is None
    guards.check_server_allowed("https://citeck.ecos24.ru")


def test_allowed_servers_rejects_other_url(monkeypatch):
    monkeypatch.setenv(guards.ALLOWED_SERVERS_ENV, "http://localhost")
    with pytest.raises(guards.GuardError, match="not in CITECK_ALLOWED_SERVERS"):
        guards.check_server_allowed("https://enterprise.ecos24.ru")


def test_allowed_servers_normalizes_slash_and_case(monkeypatch):
    monkeypatch.setenv(guards.ALLOWED_SERVERS_ENV, " HTTP://Localhost/ , http://127.0.0.1 ")
    guards.check_server_allowed("http://localhost")
    guards.check_server_allowed("http://127.0.0.1/")


def test_records_request_refuses_server_outside_allowlist(monkeypatch):
    monkeypatch.setenv(guards.ALLOWED_SERVERS_ENV, "http://localhost")
    config_dir = _credentials("https://enterprise.ecos24.ru")
    with patch("lib.records_api.auth.get_auth_header") as auth_header, \
         patch("lib.records_api.urllib.request.urlopen") as urlopen:
        with pytest.raises(records_api.RecordsApiError, match="not in CITECK_ALLOWED_SERVERS"):
            records_api.records_query("emodel/type", config_dir=config_dir)
    auth_header.assert_not_called()
    urlopen.assert_not_called()


def test_generation_mode_off_allows_artifact_source(monkeypatch):
    monkeypatch.delenv(guards.GENERATION_MODE_ENV, raising=False)
    guards.check_mutation_allowed([{"id": "emodel/type@x", "attributes": {}}])


@pytest.mark.parametrize("record_id", [
    "emodel/type@", "emodel/type@ws:deal", "uiserv/form@x", "uiserv/journal@x", "eproc/bpmn-def@x",
    "emodel/perms@ws:deal", "uiserv/menu@x", "eapps/ecosapp@", "emodel/workspace@", "type@deal",
    "EMODEL/TYPE@deal", "emodel/permission-settings@", "emodel/permission-settings-repo@x",
    "emodel/authority-group@", "emodel/authority-group@purchasers",
])
def test_generation_mode_rejects_artifact_sources(monkeypatch, record_id):
    monkeypatch.setenv(guards.GENERATION_MODE_ENV, "1")
    with pytest.raises(guards.GuardError, match="deploy_app"):
        guards.check_mutation_allowed([{"id": "emodel/ws-deal@", "attributes": {}},
                                       {"id": record_id, "attributes": {}}])


@pytest.mark.parametrize("record_id", [
    "emodel/deal@", "emodel/deal@123", "emodel/workspace-member@", "emodel/person@fet",
])
def test_generation_mode_allows_data_records(monkeypatch, record_id):
    monkeypatch.setenv(guards.GENERATION_MODE_ENV, "true")
    guards.check_mutation_allowed([{"id": record_id, "attributes": {"title": "x"}}])


def test_generation_mode_rejects_action_on_bpmn_def(monkeypatch):
    monkeypatch.setenv(guards.GENERATION_MODE_ENV, "yes")
    with pytest.raises(guards.GuardError):
        guards.check_mutation_allowed([{"id": "eproc/bpmn-def@", "attributes": {"action": "DEPLOY"}}])


async def test_records_mutate_tool_refuses_in_generation_mode(client: Client, monkeypatch):
    monkeypatch.setenv(guards.GENERATION_MODE_ENV, "1")
    config_dir = _credentials()
    with patch("servers.citeck_mcp.lib_records_mutate") as mutate, \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("records_mutate", {
            "records": [{"id": "emodel/type@", "attributes": {"id": "deal"}}]})
    assert result.data["ok"] is False
    assert result.data["refused"] is True
    mutate.assert_not_called()


async def test_records_mutate_returns_platform_error_text(client: Client, monkeypatch):
    monkeypatch.delenv(guards.GENERATION_MODE_ENV, raising=False)
    config_dir = _credentials()
    body = '{"messages":[{"level":"ERROR","msg":{"type":"EcosWebException","msg":"Source is not found"}}]}'
    error = records_api.ServerError("Server error: HTTP 500", status_code=500, response_body=body)
    with patch("servers.citeck_mcp.lib_records_mutate", side_effect=error), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("records_mutate", {"records": [{"id": "emodel/x@", "attributes": {}}]})
    assert result.data["ok"] is False
    assert result.data["platform_errors"] == ["Source is not found"]



@pytest.mark.parametrize("record", [
    {"id": "emodel/other:deal@123", "attributes": {"title": "x"}},
    {"id": "emodel/gen-ws:deal@", "attributes": {"_workspace": "other"}},
    {"id": "emodel/workspace-member@", "attributes": {"_parent": "emodel/workspace@other"}},
])
def test_generation_mode_rejects_records_of_other_workspaces(monkeypatch, record):
    monkeypatch.setenv(guards.GENERATION_MODE_ENV, "1")
    monkeypatch.setenv(guards.GEN_WORKSPACE_ENV, "gen-ws")
    with pytest.raises(guards.GuardError, match="other workspaces"):
        guards.check_mutation_allowed([record])


@pytest.mark.parametrize("record", [
    {"id": "emodel/gen-ws:deal@", "attributes": {"_workspace": "gen-ws", "title": "x"}},
    {"id": "emodel/gen_ws:deal@1", "attributes": {}},
    {"id": "emodel/workspace-member@", "attributes": {"_parent": "emodel/workspace@gen-ws"}},
    {"id": "emodel/person@fet", "attributes": {"firstName": "x"}},
])
def test_generation_mode_allows_records_of_own_workspace(monkeypatch, record):
    monkeypatch.setenv(guards.GENERATION_MODE_ENV, "1")
    monkeypatch.setenv(guards.GEN_WORKSPACE_ENV, "gen-ws")
    monkeypatch.setattr(guards, "_known_workspaces", {"gen-ws", "gen_ws"})
    guards.check_mutation_allowed([record])
