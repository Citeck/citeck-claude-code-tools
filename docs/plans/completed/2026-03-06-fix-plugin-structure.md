# Fix Plugin Structure

## Overview
- Fix Citeck Claude Code plugin to comply with official Claude Code plugin guidelines
- Replace relative script paths with `${CLAUDE_SKILL_DIR}` for correct resolution after marketplace installation
- Fix `allowed-tools` patterns to match absolute paths
- Add custom agents for delegating complex multi-step operations
- Add `context: fork` for self-contained workflow skills

## Context (from discovery)
- Plugin root: `plugins/citeck/`
- Skills: `citeck-auth`, `citeck-records`, `citeck-tracker`, `citeck-changes-to-task`
- Shared lib: `plugins/citeck/lib/` (auth.py, config.py, records_api.py, pkce.py)
- Tests: `plugins/citeck/tests/`
- Official docs: https://code.claude.com/docs/en/plugins, /en/skills, /en/sub-agents

## Development Approach
- **Testing approach**: Regular (code first, then tests)
- Complete each task fully before moving to the next
- Make small, focused changes
- **CRITICAL: every task MUST include new/updated tests** for code changes in that task
- **CRITICAL: all tests must pass before starting next task**
- **CRITICAL: update this plan file when scope changes during implementation**
- Run tests after each change

## Testing Strategy
- **Unit tests**: update existing tests in `plugins/citeck/tests/` where behavior changes
- Validate SKILL.md frontmatter manually via `claude --plugin-dir ./plugins/citeck`

## Progress Tracking
- Mark completed items with `[x]` immediately when done
- Add newly discovered tasks with + prefix
- Document issues/blockers with warning prefix
- Update plan if implementation deviates from original scope

## Implementation Steps

### Task 1: Fix script paths in citeck-records SKILL.md
- [x] Read `plugins/citeck/skills/citeck-records/SKILL.md`
- [x] Replace all `python3 scripts/` with `python3 ${CLAUDE_SKILL_DIR}/scripts/`
- [x] Update `allowed-tools` from `Bash(python3 scripts/*)` to `Bash(python3 *)`
- [x] Verify frontmatter is valid YAML
- [x] Run existing tests: `cd plugins/citeck && python3 -m pytest tests/test_records_scripts.py -v`

### Task 2: Fix script paths in citeck-auth SKILL.md
- [x] Read `plugins/citeck/skills/citeck-auth/SKILL.md`
- [x] Replace all `python3 scripts/` with `python3 ${CLAUDE_SKILL_DIR}/scripts/`
- [x] Update `allowed-tools` from `Bash(python3 scripts/*)` to `Bash(python3 *)`
- [x] Verify frontmatter is valid YAML
- [x] Run existing tests: `cd plugins/citeck && python3 -m pytest tests/test_auth_skill.py -v`

### Task 3: Fix script paths in citeck-tracker SKILL.md
- [x] Read `plugins/citeck/skills/citeck-tracker/SKILL.md`
- [x] Replace all `python3 scripts/` with `python3 ${CLAUDE_SKILL_DIR}/scripts/`
- [x] Update `allowed-tools` from `Bash(python3 scripts/*)` to `Bash(python3 *)`
- [x] Verify frontmatter is valid YAML
- [x] Run existing tests: `cd plugins/citeck && python3 -m pytest tests/test_tracker.py -v`

### Task 4: Fix script paths in citeck-changes-to-task SKILL.md
- [x] Read `plugins/citeck/skills/citeck-changes-to-task/SKILL.md`
- [x] Replace all script paths with `${CLAUDE_SKILL_DIR}/scripts/` prefix
- [x] Fix hardcoded path `plugins/citeck/skills/citeck-changes-to-task/scripts/create_from_taskmd.py` to `${CLAUDE_SKILL_DIR}/scripts/create_from_taskmd.py`
- [x] Fix `allowed-tools`: change `Bash(git:*, python3 *)` to `Bash(git *, python3 *)`
- [x] Add `context: fork` to frontmatter (self-contained workflow)
- [x] Verify frontmatter is valid YAML
- [x] Run existing tests: `cd plugins/citeck && python3 -m pytest tests/test_changes_to_task.py -v`

### Task 5: Fix license in plugin.json
- [x] Read `plugins/citeck/.claude-plugin/plugin.json`
- [x] Change `"license": "GNU"` to valid SPDX identifier (e.g., `"GPL-3.0-only"`)

### Task 6: Create citeck-explorer custom agent
- [x] Create `plugins/citeck/agents/` directory
- [x] Create `plugins/citeck/agents/citeck-explorer.md` with:
  - name: citeck-explorer
  - description: Read-only agent for exploring Citeck ECOS data via Records API. Use proactively when investigating records, searching data, or exploring record structure.
  - tools: Bash, Read, Grep, Glob (read-only, no Write/Edit)
  - model: inherit
  - skills: citeck-records (preloaded)
  - System prompt with instructions for data exploration
- [x] Verify agent file has valid YAML frontmatter

### Task 7: Create citeck-manager custom agent
- [x] Create `plugins/citeck/agents/citeck-manager.md` with:
  - name: citeck-manager
  - description: Agent for managing Citeck Project Tracker issues — creating, updating, searching tasks. Use proactively for multi-step tracker operations.
  - tools: Bash, Read, Grep, Glob, AskUserQuestion (needs user confirmation)
  - model: inherit
  - skills: citeck-tracker (preloaded)
  - System prompt with instructions for issue management workflow
- [x] Verify agent file has valid YAML frontmatter

### Task 8: Update tests for path changes
- [x] Check if any tests reference old script paths or patterns
- [x] Update tests that validate SKILL.md content or frontmatter
- [x] Run full test suite: `cd plugins/citeck && python3 -m pytest tests/ -v`
- [x] All tests must pass

### Task 9: Verify acceptance criteria
- [x] All SKILL.md files use `${CLAUDE_SKILL_DIR}/scripts/` paths
- [x] All `allowed-tools` patterns match absolute paths (`Bash(python3 *)`, `Bash(git *, python3 *)`)
- [x] `citeck-changes-to-task` has `context: fork` in frontmatter
- [x] Two custom agents exist in `plugins/citeck/agents/`
- [x] License is valid SPDX identifier
- [x] Run full test suite: `cd plugins/citeck && python3 -m pytest tests/ -v`
- [x] Test plugin locally: `claude --plugin-dir ./plugins/citeck` (manual - structure validated programmatically)

### Task 10: [Final] Update documentation
- [x] Update README.md to document new agents
- [x] Update plugin version in plugin.json (2.0.0 -> 3.0.0)

## Technical Details

### ${CLAUDE_SKILL_DIR} substitution
- Replaced in SKILL.md content **before** Claude sees it
- For plugin skills: resolves to the skill's subdirectory within the plugin (e.g., `~/.claude/plugins/cache/.../skills/citeck-records/`)
- Ensures scripts are found regardless of working directory or installation location

### Custom agents architecture
```
User request → Claude (main context)
                 ├── simple query → citeck-tracker skill (inline)
                 ├── explore data → delegates to citeck-explorer agent
                 │                    └── preloaded: citeck-records
                 └── create/update issue → delegates to citeck-manager agent
                                            └── preloaded: citeck-tracker
```

- Claude decides when to delegate based on agent description
- Simple queries ("show my tasks") stay inline via skill
- Complex operations ("create issue from changes") go to agent
- citeck-changes-to-task runs as `context: fork` (always a self-contained workflow)

### allowed-tools pattern matching
- `Bash(python3 scripts/*)` — matches `python3 scripts/query.py` (relative)
- `Bash(python3 *)` — matches `python3 /any/absolute/path/query.py` (absolute)
- After `${CLAUDE_SKILL_DIR}` substitution, Claude sees absolute paths, so patterns must be broad

## Post-Completion

**Manual verification:**
- Load plugin with `claude --plugin-dir ./plugins/citeck`
- Test each skill invocation (`/citeck:citeck-records`, `/citeck:citeck-tracker`)
- Verify agents appear in `/agents`
- Test that citeck-explorer and citeck-manager are auto-delegated
- Install via marketplace and verify scripts resolve correctly
