# Citeck tools

This repository packages one Python MCP server and five shared skills for local Claude Code
and Codex CLI. Read `CLAUDE.md` for architecture and testing conventions.

- Server and shared libraries: `plugins/citeck/servers/`, `plugins/citeck/lib/`.
- Skills and their resources: `plugins/citeck/skills/`.
- Tests: `plugins/citeck/tests/`; run `uv run python -m pytest tests/ -v` in `plugins/citeck`.
  No Maven build is needed. Inspect the test verdict in the complete log.
- Claude manifest: `plugins/citeck/.claude-plugin/plugin.json`, MCP: `.mcp.json`.
- Codex manifest: `plugins/citeck/.codex-plugin/plugin.json`, MCP: `.mcp.codex.json`.
- Catalogs: `.claude-plugin/marketplace.json`, `.agents/plugins/marketplace.json`.
  Keep manifest names and versions consistent; Python project version has a separate purpose.
- Installation: `README.md`; changes: `RELEASE_NOTES.md`.
- Adaptation progress and remaining checks: `docs/plans/2026-10-05-codex-plugin-adaptation.md`.

Skills are shared by both clients; follow these rules:
- Frontmatter keys stay within the Agent Skills spec (`name`, `description`, `license`,
  `compatibility`, `metadata`, `allowed-tools`). `allowed-tools` pre-approves tools in Claude Code
  and uses `mcp__plugin_citeck_citeck__<tool>` names; Codex ignores it.
- Skill bodies name MCP tools without a client prefix and use `${CLAUDE_SKILL_DIR}` for paths.
  Claude Code substitutes it only in `SKILL.md`; the preamble tells other clients to use the
  `SKILL.md` directory. Referenced files use `${SKILL_DIR}`/`<SKILL_DIR>` for the same value.
- Do not use `context: fork` (forked skills cannot ask the user), `` !`cmd` `` or `$ARGUMENTS`.
- Codex display and invocation policy: `skills/<name>/agents/openai.yaml`.
Preserve issue preview/confirmation and explicit target profiles.
Never log credentials or tokens, or modify a user's client configuration during package tests.
Use isolated temporary profiles for installation checks. Commit and publication require a
separate user instruction for this adaptation.
