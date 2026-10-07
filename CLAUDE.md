# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Plugin for local Claude Code and Codex CLI providing MCP server and skills for the [Citeck ECOS](https://www.citeck.ru/) platform. Everything lives under `plugins/citeck/`.

## Commands

```bash
# Run all tests (uv required — installs fastmcp dependency)
cd plugins/citeck && uv run python -m pytest tests/ -v

# Run a single test file
cd plugins/citeck && uv run python -m pytest tests/test_config.py -v

# Run a single test case
cd plugins/citeck && uv run python -m pytest tests/test_config.py::TestConfig::test_save_and_get_credentials -v

# Test plugin locally
claude --plugin-dir ./plugins/citeck
```

No build step. No linter config in the repo (ruff is used externally).

## Architecture

### Component relationships

```
MCP Server (FastMCP, persistent process)
  └── provides tools: ping, test_connection, reauthenticate, records_query, records_mutate,
      list_projects, set_project_default, list_profiles, set_active_profile,
      set_docs_profile, set_ept_profile, set_records_profile,
      search_issues, preview_issue, create_issue, update_issue,
      preview_comment, add_comment, query_sprints,
      query_components, query_tags, query_releases, query_comments,
      download_attachment, search_docs
  └── imports shared modules from lib/
Skills (user-invocable via /citeck:<name>)
  └── citeck-auth: PKCE browser flow (runs Python scripts)
  └── citeck-ask-docs: RAG search over citeck-docs (uses MCP search_docs)
  └── citeck-changes-to-task: workflow orchestration (uses MCP tools)
  └── citeck-changes-to-task-md: generates task.md from git changes
  └── citeck-test-feature: feature acceptance testing (MCP + browser tools + HTTP)
```

### MCP Server (`servers/citeck_mcp.py`)

The primary transport layer. A single FastMCP process runs persistently, providing all Citeck tools via the MCP protocol. Benefits over the previous script-based approach:
- Persistent auth session — no cold start per call
- Clean UX: one `create_issue` tool call instead of 7 Bash calls (the client adds its own prefix, e.g. `mcp__plugin_citeck_citeck__create_issue` in Claude Code)
- In-memory caching (e.g., project list)

Started via `uv run` (see `.mcp.json`). Dependencies managed by `pyproject.toml`.

### Shared library (`lib/`)

- **config.py** — multi-profile credential management (`~/.citeck/credentials.json`)
- **auth.py** — OIDC/Basic auth with token caching, endpoint discovery via `eis.json`
- **pkce.py** — PKCE browser-based OAuth flow
- **records_api.py** — HTTP client wrapping `/gateway/api/records/{query,mutate}`

Used by both the MCP server and remaining skill scripts (citeck-auth).

### Skill definition format

Skills under `skills/`:

- `citeck-auth` — PKCE browser flow, runs Python scripts using the client shell tool
- `citeck-ask-docs` — answers Citeck platform questions via `search_docs` with citations
- `citeck-changes-to-task` — workflow skill using MCP tools
- `citeck-changes-to-task-md` — generates task.md, uses git and file writing (no MCP)
- `citeck-test-feature` — guide + scaffolder for feature acceptance testing; `references/` (durable methodology), `examples/` (profile), `templates/` (generated plan), `scripts/` (fixture generators). Uses Citeck MCP + available Playwright MCP or browser tools + scripted HTTP

Each skill may also have `agents/openai.yaml` (Codex display name and invocation policy).

## Testing patterns

- Framework: pytest + unittest.TestCase + unittest.mock
- All tests use `tempfile.mkdtemp()` for config isolation — no external service calls
- HTTP mocking: `@patch("urllib.request.urlopen")` on lib modules
- MCP tool tests: mock lib functions, test tool input/output schemas
- Tests are in `plugins/citeck/tests/test_*.py`

## Plugin manifest

`plugins/citeck/.claude-plugin/plugin.json` declares `skills` and `mcpServers` paths. The `mcpServers` field points to `.mcp.json` which configures the FastMCP server startup via `uv run`.

## Commit style

Conventional commits: `feat:`, `fix:`, `refactor:`, `chore:`.

## Codex packaging

`.agents/plugins/marketplace.json` exposes the same plugin for Codex.
`plugins/citeck/.codex-plugin/plugin.json` uses `.mcp.codex.json` with plugin-relative `cwd`.
Both manifests must have the same name/version. Skills are shared by both clients; follow the
skill rules in `AGENTS.md`. See also
`docs/plans/2026-10-05-codex-plugin-adaptation.md` for checks and current limitations.
