# Citeck Claude Code Tools

Plugin marketplace for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) to boost development on the [Citeck](https://www.citeck.ru/) platform.

## Installation

### 1. Add the marketplace

```bash
/plugin marketplace add Citeck/citeck-claude-code-tools
```

### 2. Install the plugin

```bash
/plugin install citeck@citeck
```

After installation, skills are available with the `citeck:` prefix (e.g. `/citeck:citeck-records`).

### Update

```bash
claude plugin update citeck@citeck
```

Or enable auto-update: `/plugin` → **Marketplaces** → `citeck` → **Enable auto-update**.

## Plugin: citeck

### Getting Started

1. Install the plugin (see above)
2. Run `/citeck:citeck-auth` to configure your Citeck ECOS connection (URL, credentials)
3. Use any of the skills below

### Skills

| Skill | Description |
|-------|-------------|
| [citeck-auth](plugins/citeck/skills/citeck-auth/SKILL.md) | Configure Citeck ECOS connection — set URL, credentials, and test connectivity |
| [citeck-records](plugins/citeck/skills/citeck-records/SKILL.md) | Query Citeck Records API (search, mutate) |
| [citeck-records-query](plugins/citeck/skills/citeck-records-query/SKILL.md) | Read-only query access to Records API (no mutations) |
| [citeck-tracker](plugins/citeck/skills/citeck-tracker/SKILL.md) | Manage issues in Citeck Project Tracker — create, update, search tasks |
| [citeck-changes-to-task](plugins/citeck/skills/citeck-changes-to-task/SKILL.md) | Generate task from git changes and optionally create it in Project Tracker |

### citeck-auth

Configure and manage connections to Citeck ECOS instances. Supports multiple profiles for different environments (local, staging, production).

```bash
/citeck:citeck-auth
```

Features:
- Interactive credential setup (URL, username, password, OIDC/Basic auth)
- Multiple profiles for different environments
- Connection testing
- Profile switching

Credentials are stored in `~/.citeck/credentials.json` with restricted permissions.

### citeck-records

Query the Citeck ECOS Records API for searching records, loading attributes, and data exploration.

```bash
/citeck:citeck-records
```

Features:
- Query records with predicate language
- Load record attributes
- Create/update records (with user confirmation)
- Delete records (with user confirmation)

### citeck-tracker

Manage issues in Citeck ECOS Project Tracker.

```bash
/citeck:citeck-tracker
```

Features:
- List projects and workspaces
- Search/filter issues by project, status, assignee, type
- Create issues (task, story, bug, epic) with dry-run preview
- Update issue attributes and status with dry-run preview

### citeck-changes-to-task

Generate a structured task description from git changes and optionally create it as an issue in Citeck Project Tracker.

```bash
/citeck:citeck-changes-to-task
```

Features:
- Analyze git diff to generate task description (task.md)
- Automatic type detection (Bug, Story, Task)
- Russian-language descriptions for QA
- Optional creation in Citeck Project Tracker

### Skill Privilege Separation

The plugin intentionally provides two Records API skills with different access levels:

- **`citeck-records`** — full access (query + mutate), available as a user-invocable skill
- **`citeck-records-query`** — read-only (query only), used by the `citeck-explorer` agent

This is a deliberate architectural decision based on the principle of least privilege. The `citeck-explorer` agent is designed to be read-only — by binding it to `citeck-records-query`, the agent physically cannot access `mutate.py`, even if its prompt instructions are bypassed. The `query.py` script is shared (identical) between both skills; only the skill's `allowed-tools` differ.

### Custom Agents

| Agent | Description |
|-------|-------------|
| [citeck-explorer](plugins/citeck/agents/citeck-explorer.md) | Read-only agent for exploring Citeck ECOS data via Records API |
| [citeck-manager](plugins/citeck/agents/citeck-manager.md) | Manage Citeck Project Tracker issues — create, update, search tasks |

Agents are invoked automatically by Claude when it determines delegation is appropriate.

### Shared Library

The plugin includes a shared library (`plugins/citeck/lib/`) used by all skills:

- `config.py` — credential management with multi-profile support
- `auth.py` — OIDC and Basic Auth with token caching
- `records_api.py` — unified Records API client

## Security: ~/.citeck/ Directory

The plugin stores credentials and tokens in `~/.citeck/`:

```
~/.citeck/
├── credentials.json          # Profiles with URL, username, password (chmod 600)
└── tokens/
    └── <profile>/
        └── token.json        # Cached OIDC tokens (chmod 600)
```

The plugin automatically sets `chmod 600` on `credentials.json` when saving credentials, restricting access to the file owner only. If you create or edit the file manually, ensure proper permissions:

```bash
chmod 600 ~/.citeck/credentials.json
```

Note: passwords are stored in plaintext in `credentials.json`. This is acceptable for local development environments. Do not commit this file to version control. The `.gitignore` should already exclude it.

## Structure

```
.
├── .claude-plugin/
│   └── marketplace.json            # Marketplace catalog
└── plugins/
    └── citeck/                     # Plugin
        ├── .claude-plugin/
        │   └── plugin.json         # Plugin manifest (v3.0.0)
        ├── agents/                 # Custom agents
        │   ├── citeck-explorer.md  # Read-only data exploration agent
        │   └── citeck-manager.md   # Issue management agent
        ├── lib/                    # Shared modules
        │   ├── auth.py             # OIDC/Basic auth + token cache
        │   ├── config.py           # Credentials management
        │   └── records_api.py      # Records API client
        ├── skills/
        │   ├── citeck-auth/        # Auth setup skill
        │   ├── citeck-records/     # Records API skill (query + mutate)
        │   ├── citeck-records-query/  # Read-only Records API (for agents)
        │   ├── citeck-tracker/     # Project Tracker skill
        │   └── citeck-changes-to-task/  # Git changes to task skill
        └── tests/                  # Unit tests
```

## Contributing

1. Clone the repo and create a feature branch
2. Add your skill/agent/hook to `plugins/citeck/`
3. Update this README
4. Open a Pull Request

### Adding a skill

Create a directory under `plugins/citeck/skills/`:

```
plugins/citeck/skills/
└── your-skill-name/
    └── SKILL.md
```

The `SKILL.md` must include YAML frontmatter with `name`, `description`, and optionally `allowed-tools`.

### Testing locally

```bash
claude --plugin-dir ./plugins/citeck
```

### Running tests

```bash
cd plugins/citeck && python3 -m pytest tests/ -v
```
