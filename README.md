# Citeck Claude Code Tools

Plugin marketplace for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) to boost development on the [Citeck](https://www.citeck.ru/) platform.

## What you get

### Task creation from code changes

Run `/citeck:citeck-changes-to-task` after finishing work on a branch — Claude analyzes the diff, determines the task type (Bug / Story / Task), generates a title in English and a structured description in Russian for QA, and creates an issue in Project Tracker. No need to switch context or fill in forms manually.

### Task creation from description

You don't need code changes at all. Describe what you need in natural language — Claude creates the issue with the right type, priority, components, and tags.

### Working on tracker issues

Ask Claude to take a look at any issue by ID (e.g. "look at COREDEV-3703"). Claude will:
- Fetch the issue details and all comments
- Automatically download and analyze screenshots and images from comments — visual context is read without asking
- Understand the full picture: description, discussion, decisions, and attached screenshots
- Suggest a fix, start implementation, or answer questions about the issue

### Direct access to Records API

The plugin exposes raw `records_query` and `records_mutate` tools — the same Records API that powers the platform. This means Claude can:
- **Create test data** — populate the system with records for development and testing
- **Query any data** — search and inspect records across the platform by predicates, load attributes, paginate
- **Bulk mutations** — update multiple records at once
- **Explore data models** — discover available attributes and types by querying with `?json`

### Issue management

Beyond creation, the plugin provides full issue lifecycle tools:
- Search issues with filters (status, assignee, type, sprint, component, priority)
- Update issues — change status, reassign, update priority or description
- Browse sprints, components, tags, and releases for any project

### Ask the Citeck documentation

Run `/citeck:citeck-ask-docs <question>` to query the Citeck ECOS documentation via RAG. Claude searches `citeck-docs` semantically and synthesizes a grounded answer with citations — no need to open the docs site manually. Works for platform concepts, configuration, and APIs.

## Installation

### Prerequisites

- [uv](https://docs.astral.sh/uv/) — Python package manager (required for MCP server)

Install uv if you don't have it:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 1. Add the marketplace

```bash
/plugin marketplace add Citeck/citeck-claude-code-tools
```

### 2. Install the plugin

```bash
/plugin install citeck@citeck
```

The MCP server starts automatically via `uv run` — dependencies are installed on first launch, no manual setup needed.

After installation:
- MCP tools are available automatically (e.g. `mcp__citeck__create_issue`)
- Skills are available with the `citeck:` prefix (e.g. `/citeck:citeck-auth`)

### Update

```bash
claude plugin update citeck@citeck
```

Or enable auto-update: `/plugin` → **Marketplaces** → `citeck` → **Enable auto-update**.

## Plugin: citeck

### Getting Started

1. Install the plugin (see above)
2. Run `/citeck:citeck-auth` to configure your Citeck ECOS connection (URL, credentials)
3. Start using MCP tools or skills

### MCP Tools

The plugin provides an MCP server with the following tools, available as `mcp__citeck__<tool_name>`:

| Tool | Description |
|------|-------------|
| `ping` | Health-check: verify the MCP server is running |
| `test_connection` | Verify auth connection to Citeck ECOS |
| `records_query` | Raw Records API query — search by predicate, load by IDs |
| `records_mutate` | Raw Records API mutation — create/update records |
| `list_projects` | List projects, fetch from API |
| `set_project_default` | Set the default project for operations |
| `search_issues` | Search issues with filters (status, assignee, type, sprint, etc.) |
| `create_issue` | Create a new issue with preview support |
| `update_issue` | Update an existing issue with preview support |
| `query_comments` | Fetch comments for a record with auto-download of image attachments |
| `download_attachment` | Download a file from Citeck via authenticated session |
| `query_sprints` | List sprints for a project |
| `query_components` | List components for a project |
| `query_tags` | List tags for a project |
| `query_releases` | List releases for a project |
| `search_docs` | Semantic search over Citeck documentation (citeck-docs RAG) |
| `set_docs_profile` | Set the profile used for documentation search |

### Skills

| Skill | Description |
|-------|-------------|
| [citeck-auth](plugins/citeck/skills/citeck-auth/SKILL.md) | Configure Citeck ECOS connection — set URL, credentials, and test connectivity |
| [citeck-changes-to-task](plugins/citeck/skills/citeck-changes-to-task/SKILL.md) | Create a Citeck Project Tracker issue from current git changes |
| [citeck-changes-to-task-md](plugins/citeck/skills/citeck-changes-to-task-md/SKILL.md) | Generate task.md file with structured task description from git changes |
| [citeck-ask-docs](plugins/citeck/skills/citeck-ask-docs/SKILL.md) | Ask a question about Citeck — semantic search over citeck-docs with cited answer |

### citeck-auth

Configure and manage connections to Citeck ECOS instances. Supports multiple profiles for different environments (local, staging, production).

```bash
/citeck:citeck-auth
```

Features:
- Interactive credential setup (URL, username, password, OIDC/Basic auth)
- PKCE browser-based login (recommended, no password stored)
- Multiple profiles for different environments
- Connection testing
- Profile switching

Credentials are stored in `~/.citeck/credentials.json` with restricted permissions.

### citeck-changes-to-task

Create a Citeck Project Tracker issue directly from current git changes.

```bash
/citeck:citeck-changes-to-task
```

Features:
- Analyze git diff to generate structured task description
- Automatic type detection (Bug, Story, Task)
- Russian-language descriptions for QA
- Dry-run preview before creation
- Creates issue via MCP `create_issue` tool

### citeck-changes-to-task-md

Generate a `task.md` file with a structured task description from git changes. Does not create an issue in the tracker.

```bash
/citeck:citeck-changes-to-task-md
```

### citeck-ask-docs

Ask a question about the Citeck ECOS platform — semantic search over `citeck-docs` via RAG, answer synthesized with citations.

```bash
/citeck:citeck-ask-docs <question>
```

The RAG service is reached via the profile set as `docs_profile` in `~/.citeck/credentials.json` (falls back to the active profile). Switch it with the `set_docs_profile` MCP tool if needed.

### Shared Library

The plugin includes a shared library (`plugins/citeck/lib/`) used by the MCP server and auth scripts:

- `config.py` — credential management with multi-profile support
- `auth.py` — OIDC and Basic Auth with token caching
- `pkce.py` — PKCE browser-based OAuth flow
- `records_api.py` — unified Records API client

## Security: ~/.citeck/ Directory

The plugin stores credentials and tokens in `~/.citeck/`:

```
~/.citeck/
├── credentials.json          # Profiles with URL, username, password (chmod 600)
├── downloads/                # Downloaded attachments (images, PDFs, etc.)
└── tokens/
    └── <profile>/
        └── token.json        # Cached OIDC tokens (chmod 600)
```

The plugin automatically sets `chmod 600` on `credentials.json` when saving credentials, restricting access to the file owner only. If you create or edit the file manually, ensure proper permissions:

```bash
chmod 600 ~/.citeck/credentials.json
```

Note: passwords are stored in plaintext in `credentials.json`. This is acceptable for local development environments. Do not commit this file to version control.

## Structure

```
.
├── .claude-plugin/
│   └── marketplace.json            # Marketplace catalog
└── plugins/
    └── citeck/                     # Plugin
        ├── .claude-plugin/
        │   └── plugin.json         # Plugin manifest
        ├── .mcp.json               # MCP server config (uv run)
        ├── pyproject.toml           # Python dependencies (FastMCP)
        ├── servers/
        │   └── citeck_mcp.py       # FastMCP server — all MCP tools
        ├── lib/                     # Shared modules
        │   ├── auth.py              # OIDC/Basic auth + token cache
        │   ├── config.py            # Credentials management
        │   ├── pkce.py              # PKCE OAuth flow
        │   └── records_api.py       # Records API client
        ├── skills/
        │   ├── _shared/             # Shared prompts (task description guide)
        │   ├── citeck-auth/         # Auth setup skill (PKCE browser flow)
        │   ├── citeck-ask-docs/     # Ask Citeck docs via RAG
        │   ├── citeck-changes-to-task/     # Create issue from git changes
        │   └── citeck-changes-to-task-md/  # Generate task.md from git changes
        └── tests/                   # Unit tests
```

## Contributing

1. Clone the repo and create a feature branch
2. Add your skill/hook to `plugins/citeck/`
3. Update this README
4. Open a Pull Request

### Testing locally

```bash
claude --plugin-dir ./plugins/citeck
```

### Running tests

```bash
cd plugins/citeck && uv run python -m pytest tests/ -v
```
