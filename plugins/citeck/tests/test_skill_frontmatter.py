"""Skill files must stay valid for both Claude Code and Codex."""

import re
from pathlib import Path

import pytest
import yaml


PLUGIN = Path(__file__).resolve().parents[1]
SKILLS = sorted((PLUGIN / "skills").glob("*/SKILL.md"))
SERVER = (PLUGIN / "servers" / "citeck_mcp.py").read_text()
CLAUDE_MCP_PREFIX = "mcp__plugin_citeck_citeck__"


def split_skill(path: Path) -> tuple[dict, str]:
    _, head, body = path.read_text().split("---\n", 2)
    return yaml.safe_load(head), body


def frontmatter(path: Path) -> dict:
    return split_skill(path)[0]


def server_tools() -> set[str]:
    return set(re.findall(r"^@mcp\.tool(?:\([^)]*\))?\ndef (\w+)\(", SERVER, re.M))


@pytest.mark.parametrize("path", SKILLS, ids=lambda p: p.parent.name)
def test_common_fields_follow_agent_skills_spec(path):
    data = frontmatter(path)
    # Codex skill-creator validation rejects other Claude Code extensions such as argument-hint.
    assert set(data) <= {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
    assert data["name"] == path.parent.name
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", data["name"])
    assert 0 < len(data["description"]) <= 1024


@pytest.mark.parametrize("path", SKILLS, ids=lambda p: p.parent.name)
def test_allowed_tools_use_claude_plugin_names(path):
    tools = [item.strip() for item in frontmatter(path)["allowed-tools"].split(",")]
    citeck = [tool for tool in tools if tool.startswith("mcp__") and "citeck" in tool]
    assert all(tool.startswith(CLAUDE_MCP_PREFIX) for tool in citeck), citeck
    assert {tool.removeprefix(CLAUDE_MCP_PREFIX) for tool in citeck} <= server_tools()


@pytest.mark.parametrize("path", SKILLS, ids=lambda p: p.parent.name)
def test_body_uses_substituted_skill_dir_and_short_tool_names(path):
    text = split_skill(path)[1]
    assert "${SKILL_DIR}/" not in text, "Claude Code substitutes only ${CLAUDE_SKILL_DIR}"
    assert not re.search(r"mcp__(plugin_citeck_)?citeck__\w", text), "tool names are client-specific"


@pytest.mark.parametrize("path", SKILLS, ids=lambda p: p.parent.name)
def test_codex_metadata(path):
    metadata = yaml.safe_load((path.parent / "agents" / "openai.yaml").read_text())
    assert set(metadata) <= {"interface", "policy", "dependencies"}
    interface = metadata["interface"]
    assert interface["display_name"].startswith("Citeck")
    assert 0 < len(interface["short_description"]) <= 1024


def test_tracker_writes_require_explicit_codex_invocation():
    metadata = yaml.safe_load(
        (PLUGIN / "skills/citeck-changes-to-task/agents/openai.yaml").read_text())
    assert metadata["policy"]["allow_implicit_invocation"] is False
