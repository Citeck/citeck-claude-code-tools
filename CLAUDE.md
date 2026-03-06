# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Plugin for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) providing skills and agents for the [Citeck ECOS](https://www.citeck.ru/) platform. Everything lives under `plugins/citeck/`.

## Commands

```bash
# Run all tests
cd plugins/citeck && python3 -m pytest tests/ -v

# Run a single test file
cd plugins/citeck && python3 -m pytest tests/test_config.py -v

# Run a single test case
cd plugins/citeck && python3 -m pytest tests/test_config.py::TestConfig::test_save_and_get_credentials -v

# Test plugin locally
claude --plugin-dir ./plugins/citeck
```

No build step. No linter config in the repo (ruff is used externally).

## Architecture

### Component relationships

```
Agents (auto-delegated by Claude)
  └── preload Skills via `skills: [...]` in frontmatter
Skills (user-invocable via /citeck:<name>)
  └── run Python scripts from their scripts/ directory
Scripts
  └── import shared modules from lib/
```

### Shared library (`lib/`)

- **config.py** — multi-profile credential management (`~/.citeck/credentials.json`)
- **auth.py** — OIDC/Basic auth with token caching, endpoint discovery via `eis.json`
- **pkce.py** — PKCE browser-based OAuth flow
- **records_api.py** — HTTP client wrapping `/gateway/api/records/{query,mutate}`

Scripts import lib via relative path insertion:
```python
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from lib.records_api import records_query
```

### Privilege separation: citeck-records vs citeck-records-query

Two Records API skills exist intentionally — this is a least-privilege architecture:

- **`citeck-records`** — full access (query.py + mutate.py), used as a user-invocable skill
- **`citeck-records-query`** — read-only (query.py only), used exclusively by the `citeck-explorer` agent

The `citeck-explorer` agent is designed to be read-only. By binding it to `citeck-records-query`, the agent physically cannot access `mutate.py` even if prompt instructions are bypassed. The `query.py` script is identical in both skills; only `allowed-tools` in the frontmatter differs.

Do NOT merge these skills or remove `citeck-records-query` — this separation is intentional.

### Skill definition format

Each skill is a directory under `skills/` with a `SKILL.md` containing YAML frontmatter:

```yaml
---
name: skill-name
description: "What the skill does"
allowed-tools: Bash(python3 */skills/skill-name/scripts/*.py *), AskUserQuestion
---
```

- `allowed-tools` uses glob patterns to restrict which commands the skill can execute
- `${CLAUDE_SKILL_DIR}` resolves to the skill's directory at runtime

### Agent definition format

Each agent is a `.md` file under `agents/` with YAML frontmatter:

```yaml
---
name: agent-name
description: "What the agent does"
model: inherit
tools: ["Bash", "Read", "Grep", "Glob"]
skills: ["skill-name"]
---
```

## Testing patterns

- Framework: pytest + unittest.TestCase + unittest.mock
- All tests use `tempfile.mkdtemp()` for config isolation — no external service calls
- HTTP mocking: `@patch("urllib.request.urlopen")` on lib modules
- Tests are in `plugins/citeck/tests/test_*.py`

## Plugin manifest

`plugins/citeck/.claude-plugin/plugin.json` declares paths to agents and skills directories. Both `"agents"` and `"skills"` fields must be present for Claude Code to discover them.

## Commit style

Conventional commits: `feat:`, `fix:`, `refactor:`, `chore:`.
