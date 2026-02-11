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

### Skills

| Skill | Description |
|-------|-------------|
| [citeck-records](plugins/citeck/skills/citeck-records/SKILL.md) | Query Citeck Records API (search, mutate, delete) on a local instance |

## Structure

```
.
├── .claude-plugin/
│   └── marketplace.json            # Marketplace catalog
└── plugins/
    └── citeck/                # Plugin
        ├── .claude-plugin/
        │   └── plugin.json         # Plugin manifest
        ├── skills/                 # Skills (SKILL.md)
        ├── agents/                 # Subagents (future)
        └── hooks/                  # Hooks (future)
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
