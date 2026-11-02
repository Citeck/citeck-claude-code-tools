# Citeck Tools for Claude Code, Codex and Pi

Plugin marketplace and Pi package for local Claude Code, Codex CLI and Pi to support development on the [Citeck](https://www.citeck.ru/) platform.

## What you get

### Task creation from code changes

Run `/citeck:citeck-changes-to-task` after finishing work on a branch — The assistant analyzes the diff, determines the task type (Bug / Story / Task), generates a title in English and a structured description in Russian for QA, and creates an issue in Project Tracker. No need to switch context or fill in forms manually.

### Task creation from description

You don't need code changes at all. Describe what you need in natural language — The assistant creates the issue with the right type, priority, components, and tags.

### Working on tracker issues

Ask your coding assistant to take a look at any issue by ID (e.g. "look at COREDEV-3703"). The assistant will:
- Fetch the issue details and all comments
- Automatically download and analyze screenshots and images from comments — visual context is read without asking
- Understand the full picture: description, discussion, decisions, and attached screenshots
- Suggest a fix, start implementation, or answer questions about the issue

### Direct access to Records API

The plugin exposes raw `records_query` and `records_mutate` tools — the same Records API that powers the platform. This means The assistant can:
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

Run `/citeck:citeck-ask-docs <question>` to query the Citeck ECOS documentation via RAG. The assistant searches `citeck-docs` semantically and synthesizes a grounded answer with citations — no need to open the docs site manually. Works for platform concepts, configuration, and APIs.

## Installation

### Prerequisites

- [uv](https://docs.astral.sh/uv/) — Python package manager (required for MCP server)

Install uv if you don't have it:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

The MCP server runs on CPython 3.11–3.14: `uv` uses an installed interpreter from this range or downloads one on first start.

### Pi

Requires Pi with the built-in MCP registration API (tested with
`@earendil-works/pi-coding-agent` **1.4.0**) and `uv` on PATH.
Install the package from this repository after the Pi changes are published:

```bash
pi install git:github.com/Citeck/citeck-claude-code-tools
```

For development, install the working copy instead:

```bash
pi install /absolute/path/to/citeck-claude-code-tools/plugins/citeck
```

The full Pi package lives in `plugins/citeck/package.json`, next to the Claude
Code and Codex manifests; its extension and tests live in `plugins/citeck/pi/`.
The repository-root `package.json` is only a private Git-install bridge pointing
to those same resources, because Pi's Git installer does not select subdirectories.
Installing the repository root locally is also supported; choose either the root
or the nested package, not both, to avoid duplicate registration.

Restart Pi or run `/reload`. The package loads the existing five skills and
registers the existing Python MCP server automatically; no manual `mcp.json`
entry or separate MCP adapter is required. In a trusted project, `pi install -l`
can be used for project-scoped installation instead of a personal install.

```text
/skill:citeck-auth
/skill:citeck-ask-docs Как настроить тип данных?
/skill:citeck-changes-to-task-md
/skill:citeck-changes-to-task
/skill:citeck-test-feature
```

For PKCE login the assistant uses the package's `citeck_auth` tool: it starts the
auth process and shows the login link while waiting. Open the link in your host
browser. On Lima add the forwarding rule below once. The Pi package automatically
uses callback port **19433** and detects Lima guest-agent markers to select the
guest bind address; no `export`, shell-profile edits or Python commands are needed. The automatic callback finishes login without copying a callback URL or
running a Python command yourself. Initial setup accepts an optional `client_id`
for a custom public OAuth client. Repeat login uses `reauth: true` for the explicit
existing profile and updates tokens without recreating the profile; it does not
accept a new URL or client ID. After login, MCP `test_connection` can check only
the active profile; use the auth skill's explicit-profile script procedure for
another profile without switching shared defaults.
The tool terminates its POSIX subprocess group on cancellation, shutdown or a
five-minute deadline; only one auth attempt runs at a time in this Pi session.
Do not perform simultaneous token/profile writes from other clients.

Use **`/mcp` inside Pi** to inspect the `citeck` connection. Tools use
`mcp__citeck__<tool>` names and default to deferred exposure, discoverable with
`tool_search` or codemode. `pi mcp list` outside the session does not load package
extensions and cannot validate this registration. A user `mcp.json` entry named
`citeck` takes precedence; exposure/enabled changes for extension registrations
through `/mcp` are session-only. Do not install a replacement `/mcp` adapter
alongside the built-in integration. Missing `uv` or disabled MCP must be resolved
before calling server tools; skills alone do not establish a connection.

Pi does not enforce the Codex skill invocation policy from `agents/openai.yaml`.
Issue creation still requires the user's request, complete preview and explicit
confirmation; exposure is not a permission boundary. Large previews must be
retrieved and displayed completely before confirmation, or creation stops.
Browser automation for feature testing is a separate optional dependency, not
installed by this package.

The supported Pi target is **the entire process running in one POSIX local/VM
or container environment**, with shared paths for MCP, auth and attachments.
Host Pi with a separately sandboxed shell, Windows process-tree cancellation,
and interactive authorization in RPC/print clients are not verified. The package
never asks for callback codes or tokens in chat. Authorization URLs shown to the
user may appear in progress/session output; tokens and callback responses must not.
`CITECK_CONFIG_DIR`, if set, selects the same credential directory for the MCP
server and PKCE setup; normally both use `~/.citeck/`.

Update and remove using the same source you installed:

```bash
pi update git:github.com/Citeck/citeck-claude-code-tools
pi remove git:github.com/Citeck/citeck-claude-code-tools
```

Local installation, resource discovery, extension lifecycle and relocated MCP
smoke checks were tested without production access. Live Mac/Lima/Keycloak login
and remote Git installation of these unpublished changes remain unverified.

### Codex CLI

Локальная установка проверена в Codex CLI `0.160.0`:

```bash
codex plugin marketplace add /absolute/path/to/citeck-claude-code-tools
codex plugin add citeck@citeck
codex plugin list --json
```

После изменения локального пакета обновите каталог и повторите установку:

```bash
codex plugin add citeck@citeck
```

Откройте новую сессию. Codex загружает установленную копию плагина; изменения исходников
не изменяют уже запущенный MCP-процесс. Каталог Git будет содержать адаптацию после публикации
соответствующего commit; текущая проверка относится к локальной установке.

В Codex выберите `$citeck:citeck-auth`, `$citeck:citeck-ask-docs`,
`$citeck:citeck-changes-to-task`, `$citeck:citeck-changes-to-task-md` или
`$citeck:citeck-test-feature` в списке навыков. Можно описать задачу обычным текстом.
`$citeck:citeck-changes-to-task` создаёт записи в трекере, поэтому Codex запускает его только
при явном выборе. В Claude Code используйте `/citeck:<skill-name>`. Оба клиента читают общие
файлы навыков; в Claude Code поле `allowed-tools` заранее разрешает команды и инструменты навыка.

Первый запуск `uv` устанавливает зависимости и требует доступа к Python-репозиторию.
В конфигурации Codex задано `startup_timeout_sec = 180` и `tool_timeout_sec = 300`:
повтор PKCE после отклонения scope может ждать два раза по 120 секунд, затем обменять код
на токены. При изменении параметра `reauthenticate.timeout` увеличьте общий предел клиента.
Авторизацию выполняет Citeck через `~/.citeck/`; `codex mcp login` её не заменяет.
Перед запросами проверяйте профили и адреса через `list_profiles`; для отдельных операций
передавайте `profile` явно. Изменяйте общие профили и настройки авторизации последовательно:
текущее хранилище `~/.citeck/` не блокирует одновременную запись из двух клиентов. Разрешения и песочница каждого клиента действуют независимо.

Приёмка UI через Playwright по умолчанию выполняется в видимом окне, чтобы пользователь
мог наблюдать действия. Скрытый режим должен быть явно выбран или согласован для CI.
Проверка UI требует отдельного доступного браузерного инструмента с навигацией, вводом,
загрузкой файлов, снимками экрана и наблюдением за ошибками консоли и сети. Плагин Citeck
его не устанавливает. Если делегирование запрещено или недоступно, тестовые задания
выполняются последовательно с теми же критериями результата.

Поддерживаемые цели этого выпуска — локальные CLI. Проверки CLI не подтверждают работу
настольного приложения, IDE, удалённого выполнения или Codex Cloud. Подробные результаты
и невыполненные проверки записаны в
[плане адаптации](docs/plans/2026-10-05-codex-plugin-adaptation.md).

### Option A: from the shell (recommended)

Run these commands in a regular terminal (not inside a Claude Code session):

```bash
claude plugin marketplace add Citeck/citeck-claude-code-tools
claude plugin install citeck@citeck
```

`citeck@citeck` means `<plugin>@<marketplace>`. Verify with:

```bash
claude plugin list
```

### Option B: from inside a Claude Code session

Start `claude` in a terminal and type the slash commands at the prompt (they are interactive commands of the Claude Code CLI, not shell commands):

```
/plugin marketplace add Citeck/citeck-claude-code-tools
/plugin install citeck@citeck
```

Or run `/plugin` and use the interactive UI: **Marketplaces** → **Add marketplace**, then **Discover** → `citeck` → **Install**.

> Note: slash commands work only in the terminal CLI. The Claude desktop app and IDE extensions pick up plugins installed via Option A.

### Local development (no install)

To try the plugin straight from this repository:

```bash
claude --plugin-dir ./plugins/citeck
```

The MCP server starts automatically via `uv run` — dependencies are installed on first launch, no manual setup needed.

After installation:
- MCP tools are available automatically (in Claude Code as `mcp__plugin_citeck_citeck__<tool_name>`, e.g. `mcp__plugin_citeck_citeck__create_issue`)
- Skills are available with the `citeck:` prefix (e.g. `/citeck:citeck-auth`)

### Browser authentication inside a Lima VM

PKCE can receive the browser callback automatically from the Mac through Lima
port forwarding. No callback URL needs to be pasted into the assistant.

**Pi:** the installed package automatically sets port `19433` for both its auth
tool and MCP server. Inside a detected Lima guest (`/run/lima-guestagent` or
`/run/lima-boot-done`), it binds the callback listener to `0.0.0.0`; elsewhere it
uses `127.0.0.1`. The browser redirect always uses `127.0.0.1`. This requires no
shell environment configuration and does not change global process settings.

**Claude Code / Codex, or custom overrides:** the shared Python library still
supports explicit settings before starting the client:

```bash
export CITECK_PKCE_CALLBACK_PORT=19433
# Only when guest forwarding requires it, inside a trusted VM:
export CITECK_PKCE_CALLBACK_HOST=0.0.0.0
```

Explicit environment settings override the Pi package defaults. Custom ports
must also be reflected in the host-side Lima rule.

Add the Citeck rule before the final deny rule in the Lima configuration:

```yaml
portForwards:
  - guestPort: 19432  # Plannotator, if used
    hostIP: "127.0.0.1"
    hostPort: 19432
  - guestPort: 19433  # Citeck OAuth callback
    hostIP: "127.0.0.1"
    hostPort: 19433
  - guestIP: "0.0.0.0"
    guestIPMustBeZero: false
    proto: any
    ignore: true
```

Apply the VM configuration using your Lima restart workflow. Start authentication
through the client as usual and open its login link in the **Mac browser**.
The redirect `http://127.0.0.1:19433/callback` is forwarded to the waiting process
in the VM. The Keycloak client must allow that loopback redirect; see the
[Keycloak configuration](plugins/citeck/README.md). The repository's documented
configuration uses `http://127.0.0.1/*`; verify the actual client accepts the URI.

These settings apply to initial PKCE setup and MCP `reauthenticate`. Outside the
Pi package, the Python library defaults to `127.0.0.1` and a random available port
(`0`), preserving existing Claude/Codex behavior. The port must be an integer from 0 to 65535; the bind host must be
`127.0.0.1` or `0.0.0.0`. With a fixed port, a bind failure stops authentication
rather than silently choosing an unforwarded port. Only one authentication attempt
can use the fixed port at a time.

Binding to `0.0.0.0` exposes the listener on guest interfaces; use a trusted VM
network and firewall, and never publish this port to an untrusted network.
The Mac forward must stay bound to `127.0.0.1`. If your Lima setup forwards a guest
loopback listener, explicitly set `CITECK_PKCE_CALLBACK_HOST=127.0.0.1` for the
narrower bind (Pi otherwise auto-selects the wildcard bind inside Lima).
This does not provide an automatic host-browser opener: on a headless VM,
open the link shown by Pi's `citeck_auth` tool in the Mac browser.

### Update

```bash
claude plugin update citeck@citeck
```

Or enable auto-update: `/plugin` → **Marketplaces** → `citeck` → **Enable auto-update**.

### Troubleshooting

**`Failed to connect` / `CONNECTION_CLOSED` for the `citeck` MCP server.** The client only reports that the server process exited. Run the server command in a terminal to see the actual `uv` or Python error:

```bash
uv run --directory "<installed-plugin-root>" python servers/citeck_mcp.py
```

In Claude Code `<installed-plugin-root>` is `~/.claude/plugins/cache/citeck/citeck/<version>` (Windows: `%USERPROFILE%\.claude\plugins\cache\citeck\citeck\<version>`). A healthy server logs `Starting MCP server 'citeck'` and waits for input; stop it with `Ctrl+C`.

**`The requested interpreter resolved to Python 3.x, which is incompatible with the project's Python requirement`.** The server supports CPython 3.11–3.14 (`requires-python` in `plugins/citeck/pyproject.toml`): its native dependencies publish wheels for a new Python release only some time after it comes out. Unset `UV_PYTHON` or set it to a version in this range.

**Windows, Claude desktop app: `Missing expected target directory for Python minor version link`.** The desktop app is installed as an MSIX package, and Windows redirects some of its writes under `%APPDATA%` to a private package folder. A Python that `uv` downloads from inside the app can end up behind a broken link ([astral-sh/uv#19622](https://github.com/astral-sh/uv/issues/19622)). Move uv data out of `AppData` with user environment variables, then restart the app:

```powershell
[Environment]::SetEnvironmentVariable("UV_PYTHON_INSTALL_DIR", "$env:USERPROFILE\.local\share\uv\python", "User")
[Environment]::SetEnvironmentVariable("UV_CACHE_DIR", "$env:USERPROFILE\.local\share\uv\cache", "User")
```

## Plugin: citeck

### Getting Started

1. Install the plugin (see above)
2. Run `/citeck:citeck-auth` to configure your Citeck ECOS connection (URL, credentials)
3. Start using MCP tools or skills

### MCP Tools

The plugin provides an MCP server `citeck` with the following tools. Each client adds its own prefix (in Claude Code: `mcp__plugin_citeck_citeck__<tool_name>`):

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
| `set_ept_profile` | Set the profile used for task-tracker tools (issues, projects, comments, attachments) |
| `set_records_profile` | Set the profile used for plain `records_query` / `records_mutate` |
| `list_profiles` | List configured Citeck profiles with non-sensitive metadata |
| `set_active_profile` | Switch the active profile (used as fallback by every tool group) |

### Skills

| Skill | Description |
|-------|-------------|
| [citeck-auth](plugins/citeck/skills/citeck-auth/SKILL.md) | Configure Citeck ECOS connection — set URL, credentials, and test connectivity |
| [citeck-changes-to-task](plugins/citeck/skills/citeck-changes-to-task/SKILL.md) | Create a Citeck Project Tracker issue from current git changes |
| [citeck-changes-to-task-md](plugins/citeck/skills/citeck-changes-to-task-md/SKILL.md) | Generate task.md file with structured task description from git changes |
| [citeck-ask-docs](plugins/citeck/skills/citeck-ask-docs/SKILL.md) | Ask a question about Citeck — semantic search over citeck-docs with cited answer |
| [citeck-test-feature](plugins/citeck/skills/citeck-test-feature/SKILL.md) | Design, audit and run smoke, impact or full Citeck regression with code-surface inventory, terminal E2E traceability, validated manifests and optimized tier/cluster execution |

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

### Specialized profiles

Tool groups can be routed to different environments independently of the active profile:

| Setting | Tools it affects | MCP tool |
|---------|-----------------|----------|
| `docs_profile` | `search_docs` | `set_docs_profile` |
| `ept_profile` | `search_issues`, `create_issue`, `update_issue`, `list_projects`, `set_project_default`, `query_sprints`/`components`/`tags`/`releases`, `query_comments`, `download_attachment` | `set_ept_profile` |
| `records_profile` | `records_query`, `records_mutate` | `set_records_profile` |

Each setting falls back to `active_profile` when unset. Typical use case: task tracker lives on production but records queries should run against a local Citeck.

```
set_ept_profile(profile="prod")
set_records_profile(profile="local")
```

Pass an empty string to clear a setting. Each affected tool also accepts a per-call `profile` argument for one-off overrides.

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
├── package.json                    # Pi Git-install bridge (resources only)
└── plugins/
    └── citeck/                     # Plugin
        ├── .claude-plugin/
        │   └── plugin.json         # Plugin manifest
        ├── .codex-plugin/
        │   └── plugin.json         # Codex plugin manifest
        ├── package.json           # Full Pi package manifest
        ├── pi/
        │   ├── citeck.ts          # Pi integration
        │   └── tests/             # Pi extension tests
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
        │   ├── citeck-changes-to-task-md/  # Generate task.md from git changes
        │   └── citeck-test-feature/        # Plan & run feature acceptance testing
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

### Pi extension tests

Use the installed Pi runtime (no model/API key is needed):

```bash
# Set this if Pi is not installed under `npm root -g`:
export PI_INSTALL_DIR=/absolute/path/to/node_modules/@earendil-works/pi-coding-agent
node --test plugins/citeck/pi/tests/extension.test.mjs
```

The tests use temporary workspaces, a fake `uv`, synthetic auth data and the real
Pi resource loader. They do not change your client settings or use your profiles.

### Running tests

```bash
cd plugins/citeck && uv run python -m pytest tests/ -v
```
