"""Tests for the read-only preview tools and their rendering helpers."""

import os
import sys
import tempfile

import pytest
from unittest.mock import patch

from fastmcp import Client

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from servers.citeck_mcp import (
    mcp,
    _html_to_markdown,
    _indent,
    _collect_refs,
    _resolve_ref_labels,
    _ref_link,
    _render_preview_value,
    _format_record_preview,
)
from lib.config import save_credentials, set_default_project, add_project


@pytest.fixture
async def client():
    async with Client(mcp) as c:
        yield c


def _setup_with_default_project(config_dir, project="COREDEV"):
    save_credentials(
        profile="default", url="http://localhost", username="admin", password="admin",
        client_id="sqa", client_secret="secret", auth_method="basic", config_dir=config_dir,
    )
    add_project(project, config_dir=config_dir)
    set_default_project(project, config_dir=config_dir)


# --- _html_to_markdown ---

def test_html_to_markdown_headings_and_paragraph():
    md = _html_to_markdown("<h2>Заголовок</h2><p>Текст абзаца</p>")
    assert md == "## Заголовок\nТекст абзаца"


def test_html_to_markdown_ordered_and_unordered_lists():
    md = _html_to_markdown("<ol><li>раз</li><li>два</li></ol><ul><li>точка</li></ul>")
    assert md == "1. раз\n2. два\n- точка"


def test_html_to_markdown_inline_formatting():
    md = _html_to_markdown("<p>Это <b>жирный</b>, <i>курсив</i> и <code>код</code></p>")
    assert md == "Это **жирный**, *курсив* и `код`"


def test_html_to_markdown_link():
    md = _html_to_markdown('<p>См <a href="http://x/y">тикет</a></p>')
    assert md == "См [тикет](http://x/y)"


def test_html_to_markdown_br_splits_lines():
    md = _html_to_markdown("первая<br>вторая")
    assert md == "первая\nвторая"


def test_html_to_markdown_empty():
    assert _html_to_markdown("") == ""
    assert _html_to_markdown(None) == ""


def test_html_to_markdown_div_blocks_do_not_merge():
    assert _html_to_markdown("<div>first</div><div>second</div>") == "first\nsecond"


def test_indent_skips_blank_lines():
    assert _indent("a\n\nb") == "  a\n\n  b"


# --- ref collection & resolution ---

def test_collect_refs_gathers_single_and_list():
    attrs = {
        "link-project:project?str": "emodel/project@p",
        "implementer?str": "emodel/person@u",
        "summary?str": "ignored",
        "components?assoc": ["emodel/ept-components@c1", "emodel/ept-components@c2"],
        "tags?assoc": [],
        "epicLink?str": "",
    }
    refs = _collect_refs(attrs)
    assert refs == [
        "emodel/project@p",
        "emodel/person@u",
        "emodel/ept-components@c1",
        "emodel/ept-components@c2",
    ]


def test_resolve_ref_labels_maps_id_to_disp():
    mock_load = {
        "records": [
            {"id": "emodel/project@p", "attributes": {"disp": "My Project"}},
            {"id": "emodel/person@u", "attributes": {"disp": "John Doe"}},
        ]
    }
    with patch("servers.citeck_mcp.lib_records_load", return_value=mock_load) as ml:
        labels = _resolve_ref_labels(
            ["emodel/project@p", "emodel/person@u", "emodel/project@p"], "default", "/tmp"
        )
    assert labels == {"emodel/project@p": "My Project", "emodel/person@u": "John Doe"}
    # de-duplicated before the load call
    assert ml.call_args[1]["record_ids"] == ["emodel/project@p", "emodel/person@u"]


def test_resolve_ref_labels_empty_input_skips_query():
    with patch("servers.citeck_mcp.lib_records_load") as ml:
        assert _resolve_ref_labels([], "default", "/tmp") == {}
    ml.assert_not_called()


def test_resolve_ref_labels_swallows_errors():
    with patch("servers.citeck_mcp.lib_records_load", side_effect=Exception("boom")):
        assert _resolve_ref_labels(["emodel/project@p"], "default", "/tmp") == {}


def test_ref_link_resolved_and_unresolved():
    labels = {"emodel/project@p": "My Project"}
    assert _ref_link("emodel/project@p", labels, "http://localhost") == (
        "[My Project](http://localhost/v2/dashboard?recordRef=emodel/project@p)"
    )
    assert _ref_link("emodel/project@x", labels, "http://localhost") == "⚠️ emodel/project@x (не найдено)"


# --- value rendering ---

def test_render_preview_value_type_and_priority():
    assert _render_preview_value("ept-issue-bug", "type", {}, "http://x") == "🐞 Bug"
    assert _render_preview_value("200_high", "priority", {}, "http://x") == "🟠 High"


def test_render_preview_value_empty_reflink_is_clear_marker():
    assert _render_preview_value("", "reflink", {}, "http://x") == "— (очистить)"
    assert _render_preview_value([], "reflinks", {}, "http://x") == "— (очистить)"


def test_format_record_preview_create():
    record = {
        "id": "emodel/ept-issue@",
        "attributes": {
            "_type?str": "ept-issue-bug",
            "link-project:project?str": "emodel/project@p",
            "_workspace?str": "COREDEV",
            "summary?str": "Заголовок",
            "priority?str": "300_medium",
            "description?str": "<p>Текст</p>",
        },
    }
    labels = {"emodel/project@p": "Proj"}
    text = _format_record_preview(record, labels, "http://localhost", "default", "create")
    assert "📋 Превью — Создание задачи" in text
    assert "**Тип:** 🐞 Bug" in text
    assert "[Proj](http://localhost/v2/dashboard?recordRef=emodel/project@p)" in text
    assert "**Приоритет:** 🟡 Medium" in text
    assert "**Описание:**" in text
    assert "  Текст" in text


# --- preview_issue tool ---

async def test_preview_issue_is_read_only():
    tool = await mcp.get_tool("preview_issue")
    assert tool.annotations.readOnlyHint is True


async def test_preview_issue_create_returns_text_and_record(client: Client):
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)

    mock_query = {"records": [{"attributes": {"id": "emodel/project@uuid"}}]}

    def load_side_effect(record_ids=None, attributes=None, **kw):
        if attributes == ["?json"]:
            return {"records": [{"attributes": {"?json": {"key": "COREDEV"}}}]}
        return {"records": [{"id": "emodel/project@uuid", "attributes": {"disp": "Core Dev"}}]}

    with patch("servers.citeck_mcp.lib_records_query", return_value=mock_query), \
         patch("servers.citeck_mcp.lib_records_load", side_effect=load_side_effect), \
         patch("servers.citeck_mcp.get_username", return_value=None), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("preview_issue", {
            "project": "COREDEV",
            "type": "bug",
            "summary": "Boom",
            "description": "<h3>Why</h3><p>Because</p>",
        })

    data = result.data
    assert data["ok"] is True
    assert data["preview"] is True
    assert data["record"]["attributes"]["_type?str"] == "ept-issue-bug"
    assert "🐞 Bug" in data["text"]
    assert "[Core Dev]" in data["text"]
    assert "### Why" in data["text"]


async def test_preview_issue_create_requires_type(client: Client):
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("preview_issue", {"summary": "no type"})
    data = result.data
    assert data["ok"] is False
    assert "type" in data["error"].lower()


async def test_preview_issue_update_mode(client: Client):
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)
    with patch("servers.citeck_mcp.lib_records_load", return_value={"records": []}), \
         patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("preview_issue", {
            "issue": "COREDEV-42",
            "status": "in-progress",
            "summary": "New title",
        })
    data = result.data
    assert data["ok"] is True
    assert data["preview"] is True
    assert "Обновление COREDEV-42" in data["text"]
    assert data["record"]["id"] == "emodel/ept-issue@COREDEV-42"


# --- preview_comment tool ---

async def test_preview_comment_is_read_only():
    tool = await mcp.get_tool("preview_comment")
    assert tool.annotations.readOnlyHint is True


async def test_preview_comment_renders_markdown(client: Client):
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("preview_comment", {
            "issue": "COREDEV-42",
            "text": "<p>Готово — <b>проверено</b></p>",
        })
    data = result.data
    assert data["ok"] is True
    assert data["preview"] is True
    assert "Готово — **проверено**" in data["text"]
    assert data["record"]["attributes"]["text?str"] == "<p>Готово — <b>проверено</b></p>"


async def test_preview_comment_empty_text_errors(client: Client):
    config_dir = tempfile.mkdtemp()
    _setup_with_default_project(config_dir)
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = await client.call_tool("preview_comment", {"issue": "COREDEV-42", "text": "  "})
    data = result.data
    assert data["ok"] is False
    assert "text" in data["error"].lower()
