# Citeck ECOS Claude Code Tools

Plugin marketplace for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) to boost development on the [Citeck](https://www.citeck.ru/) platform.

## Installation

### 1. Add the marketplace

```bash
/plugin marketplace add Citeck/citeck-claude-code-tools
```

### 2. Install the plugin

```bash
/plugin install citeck-ecos@citeck-ecos
```

After installation, skills are available with the `citeck-ecos:` prefix (e.g. `/citeck-ecos:citeck-records`).

### Update

```bash
claude plugin update citeck-ecos@citeck-ecos
```

Or enable auto-update: `/plugin` → **Marketplaces** → `citeck-ecos` → **Enable auto-update**.

### Team setup

Add to `.claude/settings.json` in your project — teammates will be prompted to install automatically:

```json
{
  "extraKnownMarketplaces": {
    "citeck-ecos": {
      "source": {
        "source": "github",
        "repo": "Citeck/citeck-claude-code-tools"
      }
    }
  },
  "enabledPlugins": {
    "citeck-ecos@citeck-ecos": true
  }
}
```

## Plugin: citeck-ecos

### Skills

| Skill | Description |
|-------|-------------|
| [citeck-records](plugins/citeck-ecos/skills/citeck-records/SKILL.md) | Query Citeck ECOS Records API (search, mutate, delete) on a local instance |

## Structure

```
.
├── .claude-plugin/
│   └── marketplace.json            # Marketplace catalog
└── plugins/
    └── citeck-ecos/                # Plugin
        ├── .claude-plugin/
        │   └── plugin.json         # Plugin manifest
        ├── skills/                 # Skills (SKILL.md)
        ├── agents/                 # Subagents (future)
        └── hooks/                  # Hooks (future)
```

## Contributing

1. Clone the repo and create a feature branch
2. Add your skill/agent/hook to `plugins/citeck-ecos/`
3. Update this README
4. Open a Pull Request

### Adding a skill

Create a directory under `plugins/citeck-ecos/skills/`:

```
plugins/citeck-ecos/skills/
└── your-skill-name/
    └── SKILL.md
```

The `SKILL.md` must include YAML frontmatter with `name`, `description`, and optionally `allowed-tools`.

### Testing locally

```bash
claude --plugin-dir ./plugins/citeck-ecos
```
