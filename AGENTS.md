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

Keep common skills independent of client tool names and variables. Resolve resources relative
to the installed `SKILL.md`, preserve issue preview/confirmation and explicit target profiles.
Never log credentials or tokens, or modify a user's client configuration during package tests.
Use isolated temporary profiles for installation checks. Commit and publication require a
separate user instruction for this adaptation.
