"""bpmn_validate and bpmn_layout: platform checks on a file."""

import json
import os
import socket
import sys
import tempfile
from unittest.mock import patch

import pytest
from fastmcp import Client

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib import bpmn_tools
from lib.config import save_credentials
from lib.records_api import RecordsApiError, RecordsConnectionError, ServerError
from servers.citeck_mcp import mcp

XML = '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"/>'
LAID_OUT = XML.replace("/>", "><bpmndi:BPMNDiagram/></bpmn:definitions>")


@pytest.fixture
async def client():
    async with Client(mcp) as c:
        yield c


@pytest.fixture
def env(tmp_path):
    config_dir = tempfile.mkdtemp()
    save_credentials(profile="default", url="http://localhost", username="admin", password="admin",
                     auth_method="basic", config_dir=config_dir)
    path = tmp_path / "p.bpmn.xml"
    path.write_text(XML)
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("lib.bpmn_tools._sleep") as sleep:
        yield {"path": path, "sleep": sleep}


def _timeout_error():
    error = RecordsConnectionError("Cannot connect to Citeck at http://localhost: timed out")
    error.__cause__ = socket.timeout("timed out")
    return error


async def test_validate_ok(client, env):
    with patch("lib.bpmn_tools.records_api.records_mutate", return_value={"records": [{}], "messages": []}) as m:
        result = (await client.call_tool("bpmn_validate", {"file_path": str(env["path"])})).data
    assert result["ok"] is True and result["outcome"] == "valid"
    record = m.call_args.args[0][0]
    assert record["id"] == "eproc/bpmn-def@"
    assert record["attributes"] == {"action": "VALIDATE_GENERAL_BPMN", "definition": XML}


async def test_validate_document_error_from_http_500_body(client, env):
    body = {"messages": [{"level": "ERROR", "msg": {"type": "EcosWebException",
                                                    "msg": "cvc-complex-type.4: targetNamespace"}}]}
    error = ServerError("Server error: HTTP 500", status_code=500, response_body=json.dumps(body))
    with patch("lib.bpmn_tools.records_api.records_mutate", side_effect=error):
        result = (await client.call_tool("bpmn_validate", {"file_path": str(env["path"])})).data
    assert result["outcome"] == "document_error"
    assert result["errors"] == ["cvc-complex-type.4: targetNamespace"]


async def test_validate_document_error_in_ok_response(client, env):
    body = {"messages": [{"level": "ERROR", "msg": "bad flow"}, {"level": "WARN", "msg": "w"}]}
    with patch("lib.bpmn_tools.records_api.records_mutate", return_value=body):
        result = (await client.call_tool("bpmn_validate", {"file_path": str(env["path"])})).data
    assert result["outcome"] == "document_error" and result["errors"] == ["bad flow"]


async def test_validate_service_unavailable(client, env):
    with patch("lib.bpmn_tools.records_api.records_mutate",
               side_effect=RecordsConnectionError("Cannot connect")):
        result = (await client.call_tool("bpmn_validate", {"file_path": str(env["path"])})).data
    assert result["outcome"] == "service_unavailable"


async def test_validate_500_without_messages_is_outage(client, env):
    with patch("lib.bpmn_tools.records_api.records_mutate",
               side_effect=ServerError("HTTP 500", status_code=500, response_body="<html>gateway</html>")):
        result = (await client.call_tool("bpmn_validate", {"file_path": str(env["path"])})).data
    assert result["outcome"] == "service_unavailable"


@pytest.mark.parametrize("content", ["", "   \n"])
async def test_validate_empty_file_makes_no_call(client, env, content):
    env["path"].write_text(content)
    with patch("lib.bpmn_tools.records_api.records_mutate") as m:
        result = (await client.call_tool("bpmn_validate", {"file_path": str(env["path"])})).data
    assert result["outcome"] == "bad_request"
    m.assert_not_called()


async def test_validate_missing_file(client, env):
    result = (await client.call_tool("bpmn_validate", {"file_path": str(env["path"]) + ".nope"})).data
    assert result["outcome"] == "bad_request" and "not found" in result["error"]


async def test_layout_success_rewrites_file_without_returning_xml(client, env):
    with patch("lib.bpmn_tools.records_api.request",
               return_value={"success": True, "definition": LAID_OUT, "message": "ok"}) as req:
        result = (await client.call_tool("bpmn_layout", {"file_path": str(env["path"])})).data
    assert result["outcome"] == "laid_out" and result["file_changed"] is True
    assert "definition" not in result
    assert env["path"].read_text() == LAID_OUT
    assert req.call_args.args[0] == bpmn_tools.LAYOUT_PATH
    assert req.call_args.args[1] == {"definition": XML}
    assert req.call_args.kwargs["timeout"] >= 70
    env["sleep"].assert_not_called()


async def test_layout_invalid_document_is_rejected_without_retry(client, env):
    with patch("lib.bpmn_tools.records_api.request",
               return_value={"success": False, "message": "Invalid BPMN XML format. Definition must be valid BPMN XML"}) as req:
        result = (await client.call_tool("bpmn_layout", {"file_path": str(env["path"])})).data
    assert req.call_count == 1
    assert result["outcome"] == "layout_rejected" and result["error"].startswith("Invalid BPMN XML format")
    assert result["file_changed"] is False and env["path"].read_text() == XML


async def test_layout_generic_failure_may_hide_server_timeout_no_retry(client, env):
    # BpmnAutoLayoutService wraps its own 60 s timeout as "Failed to apply auto-layout: ...".
    with patch("lib.bpmn_tools.records_api.request", return_value={
            "success": False, "message": "Failed to apply auto-layout: Failed to apply auto-layout to BPMN XML"}) as req:
        result = (await client.call_tool("bpmn_layout", {"file_path": str(env["path"])})).data
    assert req.call_count == 1
    env["sleep"].assert_not_called()
    assert result["outcome"] == "layout_failed" and "two minutes" in result["hint"]


async def test_layout_retry_succeeds(client, env):
    with patch("lib.bpmn_tools.records_api.request", side_effect=[
            RecordsConnectionError("refused"), {"success": True, "definition": LAID_OUT}]):
        result = (await client.call_tool("bpmn_layout", {"file_path": str(env["path"])})).data
    assert result["ok"] is True and result["attempts"] == 2


async def test_layout_network_error_twice_is_service_unavailable(client, env):
    with patch("lib.bpmn_tools.records_api.request", side_effect=RecordsConnectionError("refused")) as req:
        result = (await client.call_tool("bpmn_layout", {"file_path": str(env["path"])})).data
    assert req.call_count == 2 and result["outcome"] == "service_unavailable"


async def test_layout_timeout_is_unknown_without_a_second_call(client, env):
    # The platform does not cancel the first computation; a second call would overlap it.
    with patch("lib.bpmn_tools.records_api.request", side_effect=[_timeout_error()]) as req:
        result = (await client.call_tool("bpmn_layout", {"file_path": str(env["path"])})).data
    assert req.call_count == 1
    env["sleep"].assert_not_called()
    assert result["outcome"] == "unknown_after_timeout" and "two minutes" in result["hint"]
    assert env["path"].read_text() == XML


async def test_layout_empty_file_makes_no_call(client, env):
    env["path"].write_text("")
    with patch("lib.bpmn_tools.records_api.request") as req:
        result = (await client.call_tool("bpmn_layout", {"file_path": str(env["path"])})).data
    assert result["outcome"] == "bad_request"
    req.assert_not_called()


def test_layout_timeout_not_below_platform_limit():
    assert bpmn_tools.LAYOUT_TIMEOUT >= 70



@pytest.mark.parametrize("code", [502, 504])
async def test_layout_gateway_timeout_is_unknown_without_retry(client, env, code):
    # Codex round 3: the gateway may give up while the platform still computes the layout.
    with patch("lib.bpmn_tools.records_api.request",
               side_effect=ServerError(f"Server error: HTTP {code}", status_code=code)) as req:
        result = (await client.call_tool("bpmn_layout", {"file_path": str(env["path"])})).data
    assert req.call_count == 1 and result["outcome"] == "unknown_after_timeout"
    env["sleep"].assert_not_called()


async def test_layout_service_unavailable_503_is_retried(client, env):
    with patch("lib.bpmn_tools.records_api.request", side_effect=[
            ServerError("Server error: HTTP 503", status_code=503), {"success": True, "definition": LAID_OUT}]) as req:
        result = (await client.call_tool("bpmn_layout", {"file_path": str(env["path"])})).data
    assert req.call_count == 2 and result["ok"] is True



async def test_layout_writes_to_output_path_and_keeps_the_source(client, env, tmp_path):
    out = tmp_path / "app/artifacts/process/bpmn/p.bpmn.xml"
    with patch("lib.bpmn_tools.records_api.request",
               return_value={"success": True, "definition": LAID_OUT, "message": "ok"}):
        result = (await client.call_tool("bpmn_layout", {"file_path": str(env["path"]),
                                                         "output_path": str(out)})).data
    assert result["file"] == str(out) and out.read_text() == LAID_OUT
    assert env["path"].read_text() == XML
