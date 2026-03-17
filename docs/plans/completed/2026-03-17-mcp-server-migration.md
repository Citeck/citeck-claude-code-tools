# MCP Server Migration

## Overview

Переписать транспортный слой Citeck-плагина с Python-скриптов на MCP-сервер (FastMCP + uv). Вместо 7-10 вызовов `Bash(python3 .../script.py)` пользователь видит 1-2 вызова `mcp__citeck__tool(...)`. Persistent процесс — auth-сессия живёт между вызовами, нет overhead запуска Python.

**Проблемы сейчас:**
- Визуальный шум: длинные пути к скриптам в логах
- Медленность: каждый скрипт = запуск Python + HTTP запрос
- Множество последовательных вызовов для одной операции
- Ошибки из-за состояния (no default project)

**Что даст миграция:**
- Чистый UX: `mcp__citeck__create_issue(...)` вместо 7 Bash-вызовов
- Persistent auth session — один процесс, нет cold start
- Батчинг запросов внутри MCP-инструментов
- Агенты с правильными моделями (sonnet для explorer, opus для manager)

## Context

- **Текущая архитектура:** 6 скилов, 2 агента, 20 Python-скриптов, 4 lib-модуля
- **Shared library (lib/):** config.py, auth.py, pkce.py, records_api.py — переиспользуется в MCP-сервере
- **Privilege separation:** citeck-records vs citeck-records-query — заменяется на уровне агентов (tools restriction)
- **Zero dependencies → FastMCP + uv:** добавляется pyproject.toml
- **Существующие тесты:** pytest + unittest.mock, HTTP mocking через @patch("urllib.request.urlopen")

## Development Approach

- **Testing approach**: TDD (tests first)
- Complete each task fully before moving to the next
- Make small, focused changes
- **CRITICAL: every task MUST include new/updated tests** for code changes in that task
- **CRITICAL: all tests must pass before starting next task**
- **CRITICAL: update this plan file when scope changes during implementation**
- Run tests after each change
- Maintain backward compatibility during migration, clean up at the end

## Testing Strategy

- **Unit tests**: pytest + unittest.mock (existing pattern)
- **MCP tool tests**: mock Records API responses, test tool input/output schemas
- **Integration test**: запуск MCP-сервера, вызов инструмента, проверка ответа
- **Existing lib/ tests**: сохраняются без изменений (lib/ не меняется)

## Progress Tracking

- Mark completed items with `[x]` immediately when done
- Add newly discovered tasks with ➕ prefix
- Document issues/blockers with ⚠️ prefix
- Update plan if implementation deviates from original scope

## Implementation Steps

### Task 1: Project setup — pyproject.toml + uv + FastMCP skeleton

- [x] create `plugins/citeck/pyproject.toml` with fastmcp dependency
- [x] create `plugins/citeck/servers/citeck_mcp.py` — minimal FastMCP server with one dummy tool (`ping`)
- [x] create `plugins/citeck/.mcp.json` — MCP server config with `uv run`
- [x] update `plugins/citeck/.claude-plugin/plugin.json` — add `mcpServers` field pointing to `.mcp.json`
- [x] verify `uv run python servers/citeck_mcp.py` starts without errors
- [x] write test: MCP server imports correctly and ping tool exists
- [x] run tests — must pass before next task

### Task 2: MCP tool — `test_connection`

Простой инструмент для проверки что MCP + auth работают вместе.

- [x] write tests for `test_connection` tool (success case, auth failure case)
- [x] implement `test_connection` tool — calls `validate_connection()` from lib/auth.py
- [x] tool returns: `{ok, method, username, url}` on success, `{ok: false, error}` on failure
- [x] run tests — must pass before next task

### Task 3: MCP tool — `records_query`

Raw Records API query для explorer-агента и продвинутых пользователей.

- [x] write tests for `records_query` tool (query by predicate, load by IDs, error handling)
- [x] implement `records_query` tool — wraps `records_query()` and `records_load()` from lib/records_api.py
- [x] parameters: `source_id`, `query` (dict), `attributes` (dict), `record_ids` (list, optional), `language`, `page`, `workspaces`
- [x] run tests — must pass before next task

### Task 4: MCP tool — `records_mutate`

Raw Records API mutation.

- [x] write tests for `records_mutate` tool (create record, update record, error handling)
- [x] implement `records_mutate` tool — wraps `records_mutate()` from lib/records_api.py
- [x] parameters: `records` (list of {id, attributes}), `version` (default 1)
- [x] run tests — must pass before next task

### Task 5: MCP tool — `list_projects`

Список проектов из трекера + управление default project.

- [x] write tests for `list_projects` tool (fetch from API, return cached, set default)
- [x] implement `list_projects` tool — combines logic from manage_projects.py
- [x] parameters: `fetch` (bool, default false), `set_default` (str, optional)
- [x] returns: `{projects: [...], default_project: str}`
- [x] MCP-сервер кэширует список проектов в памяти (persistent process)
- [x] run tests — must pass before next task

### Task 6: MCP tool — `search_issues`

Поиск задач с фильтрами.

- [x] write tests for `search_issues` tool (filter by status, assignee, type; pagination; raw JSON mode)
- [x] implement `search_issues` tool — combines logic from query_issues.py
- [x] parameters: `project`, `status`, `assignee`, `type`, `sprint`, `limit`, `sort`, `ascending`, `raw_query` (dict, optional)
- [x] `assignee: "me"` автоматически резолвится в username
- [x] returns: formatted list of issues with key fields
- [x] run tests — must pass before next task

### Task 7: MCP tool — `create_issue`

Создание задачи в трекере с поддержкой preview.

- [x] write tests for `create_issue` tool (preview mode, actual create, project resolution, field mapping)
- [x] implement `create_issue` tool — combines logic from create_issue.py
- [x] parameters: `project`, `type`, `summary`, `description`, `priority`, `assignee`, `sprint`, `components`, `tags`, `preview` (bool, default true)
- [x] preview=true: возвращает предпросмотр без создания
- [x] preview=false: создаёт задачу, возвращает ID и ссылку
- [x] project resolution: автоматически определяет workspace из project key
- [x] run tests — must pass before next task

### Task 8: MCP tool — `update_issue`

Обновление задачи в трекере.

- [x] write tests for `update_issue` tool (update status, assignee, preview mode, workspace resolution)
- [x] implement `update_issue` tool — combines logic from update_issue.py
- [x] parameters: `issue` (ID), `status`, `assignee`, `priority`, `summary`, `description`, `preview` (bool, default true)
- [x] workspace автоматически извлекается из issue ID
- [x] run tests — must pass before next task

### Task 9: MCP tools — `query_sprints`, `query_components`, `query_tags`, `query_releases`

Вспомогательные query-инструменты для метаданных проекта.

- [x] write tests for all 4 tools (basic query, project filter)
- [x] implement `query_sprints` — wraps query_sprints.py logic
- [x] implement `query_components` — wraps query_components.py logic
- [x] implement `query_tags` — wraps query_tags.py logic
- [x] implement `query_releases` — wraps query_releases.py logic
- [x] all accept `project` parameter, use default if not specified
- [x] run tests — must pass before next task

### Task 10: Update agents — model selection + MCP tools

Агенты переключаются с Bash-скриптов на MCP-инструменты.

- [x] update `agents/citeck-explorer.md`: set `model: sonnet`, remove `skills: [citeck-records-query]`, add MCP tools restriction (records_query, list_projects, query_sprints, query_components, query_tags, query_releases only)
- [x] update `agents/citeck-manager.md`: keep `model: inherit` (Opus), remove `skills: [citeck-tracker]`, configure all MCP tools
- [x] update agent prompts to reference MCP tools instead of Python scripts
- [x] manually test: explorer agent uses sonnet and can only query
- [x] manually test: manager agent can create/update issues via MCP

### Task 11: Update skills — remove script-based skills, keep workflow skills

- [x] update `citeck-changes-to-task/SKILL.md`: replace Bash(python3 ...) with MCP tool calls
- [x] update `citeck-changes-to-task-md/SKILL.md`: no changes needed (only uses git + Write)
- [x] keep `citeck-auth/SKILL.md` — PKCE browser flow stays as scripts (cannot be MCP)
- [x] remove skill `citeck-records/` (replaced by MCP records_query + records_mutate)
- [x] remove skill `citeck-records-query/` (replaced by MCP records_query via agent restriction)
- [x] remove skill `citeck-tracker/` (replaced by MCP tools: search_issues, create_issue, update_issue, etc.)
- [x] update `citeck-auth` scripts to use `${CLAUDE_PLUGIN_ROOT}` paths correctly
- [x] run tests — must pass before next task

### Task 12: Cleanup — remove old scripts and update tests

- [x] delete `skills/citeck-records/scripts/` directory (done in Task 11 — entire skill dir removed)
- [x] delete `skills/citeck-records-query/scripts/` directory (done in Task 11 — entire skill dir removed)
- [x] delete `skills/citeck-tracker/scripts/` directory (done in Task 11 — entire skill dir removed)
- [x] update/remove old tests that tested deleted scripts (test_tracker.py, test_records_scripts.py) (done in Task 11 — tests referenced deleted scripts)
- [x] keep lib/ tests unchanged (lib/ modules still used by MCP server)
- [x] keep test_auth_skill.py (citeck-auth scripts remain)
- [x] run full test suite — all must pass

### Task 13: Verify acceptance criteria

- [x] verify: создание задачи через MCP = 1-2 вызова вместо 7
- [x] verify: explorer agent uses sonnet model
- [x] verify: explorer agent cannot call mutate tools
- [x] verify: auth via PKCE still works (skill-based)
- [x] verify: `uv run` auto-installs dependencies on fresh clone
- [x] run full test suite (unit tests)
- [x] run linter — all issues must be fixed

### Task 14: [Final] Update documentation

- [x] update CLAUDE.md — document new MCP architecture
- [x] update README.md — installation instructions with uv
- [x] update plugin.json version to 3.0.0

## Technical Details

### MCP Server Structure

```
plugins/citeck/
├── servers/
│   └── citeck_mcp.py          # FastMCP server — all tools here
├── lib/                        # Shared library (unchanged)
│   ├── config.py
│   ├── auth.py
│   ├── pkce.py
│   └── records_api.py
├── .mcp.json                   # MCP server config for plugin
├── pyproject.toml              # uv/pip dependencies
└── skills/
    ├── citeck-auth/            # Stays (PKCE browser flow)
    ├── citeck-changes-to-task/ # Stays (workflow orchestration)
    └── citeck-changes-to-task-md/ # Stays (markdown generation)
```

### MCP Tool → lib Mapping

| MCP Tool | lib Function |
|----------|-------------|
| `test_connection` | `auth.validate_connection()` |
| `records_query` | `records_api.records_query()`, `records_api.records_load()` |
| `records_mutate` | `records_api.records_mutate()` |
| `list_projects` | `records_api.records_query()` + `config.get_projects()` |
| `search_issues` | query_issues.py logic → `records_api.records_query()` |
| `create_issue` | create_issue.py logic → `records_api.records_mutate()` |
| `update_issue` | update_issue.py logic → `records_api.records_mutate()` |
| `query_sprints` | `records_api.records_query()` |
| `query_components` | `records_api.records_query()` |
| `query_tags` | `records_api.records_query()` |
| `query_releases` | `records_api.records_query()` |

### Privilege Separation (новая схема)

Вместо двух отдельных скилов (citeck-records vs citeck-records-query) — ограничение на уровне агентов:

- **citeck-explorer**: `tools: [mcp__citeck__records_query, mcp__citeck__list_projects, mcp__citeck__query_sprints, mcp__citeck__query_components, mcp__citeck__query_tags, mcp__citeck__query_releases]` — только read-only инструменты
- **citeck-manager**: все MCP-инструменты + AskUserQuestion

### UX Before vs After

**Before (7 вызовов, ~90 секунд):**
```
Bash(python3 .../manage_projects.py --list)
Bash(python3 .../manage_projects.py --fetch)
Bash(python3 .../manage_projects.py --set-default COREDEV)
Bash(python3 .../query_components.py --project COREDEV)
Bash(python3 .../query_tags.py --project COREDEV)
Bash(python3 .../create_issue.py --dry-run ...)
Bash(python3 .../create_issue.py --project COREDEV ...)
```

**After (2 вызова, ~10 секунд):**
```
mcp__citeck__create_issue(project: "COREDEV", preview: true, ...)
→ user confirms
mcp__citeck__create_issue(project: "COREDEV", preview: false, ...)
```

## Post-Completion

**Manual verification:**
- Тест создания задачи через MCP в реальном Citeck
- Тест explorer-агента с sonnet моделью
- Тест PKCE re-auth когда токены протухли
- Проверка что `claude --plugin-dir ./plugins/citeck` подхватывает MCP-сервер

**Release:**
- Bump version to 3.0.0 (breaking: skills removed, MCP required)
- Update CHANGELOG.md
- Tag release
