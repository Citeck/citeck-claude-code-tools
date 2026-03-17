# Remove Plugin Agents — Rely on Direct MCP Tool Access

## Overview

Remove `citeck-explorer` and `citeck-manager` agents from the plugin. Plugin subagents cannot access MCP tools (Claude Code security restriction — `mcpServers` field is ignored for plugin agents). The main Claude process already calls MCP tools directly and successfully.

**What changes:**
- Delete agent files from `agents/`
- Preserve valuable agent knowledge (preview protocol, field mappings) in MCP tool docstrings
- Update all documentation (CLAUDE.md, README.md, plugin README.md)

**What stays the same:**
- MCP server and all 13 tools — unchanged
- Skills (citeck-auth, citeck-changes-to-task, citeck-changes-to-task-md) — unchanged
- Shared library (lib/) — unchanged
- All existing tests — pass without modification

## Context

- **Root cause**: Claude Code plugin security restriction — plugin subagents ignore `mcpServers` field, so agents defined in `plugins/citeck/agents/` cannot call MCP tools
- **GitHub issues**: #21560, #13605, #23374 (open, high priority)
- **Current behavior**: main Claude calls MCP tools successfully; agents fail with "tools not available"
- **Files to delete**: `agents/citeck-explorer.md`, `agents/citeck-manager.md`
- **Files to update**: `servers/citeck_mcp.py` (docstrings), `CLAUDE.md`, `README.md`, `plugins/citeck/README.md`

## Development Approach

- **Testing approach**: Regular (code first, verify tests pass)
- Complete each task fully before moving to the next
- Make small, focused changes
- **CRITICAL: all tests must pass before starting next task**
- **CRITICAL: update this plan file when scope changes during implementation**
- Run tests after each change

## Testing Strategy

- **Unit tests**: existing MCP tool tests remain unchanged (tools are not modified, only docstrings)
- **Verification**: run full test suite after each task to ensure nothing breaks

## Progress Tracking

- Mark completed items with `[x]` immediately when done
- Add newly discovered tasks with ➕ prefix
- Document issues/blockers with ⚠️ prefix

## Implementation Steps

### Task 1: Enrich MCP tool docstrings with agent knowledge

Transfer critical instructions from agent prompts into tool docstrings where they'll be visible to the model at decision time.

- [x] update `create_issue` docstring: add mandatory preview protocol (always call with preview:true first, show FULL preview to user, get explicit confirmation before preview:false)
- [x] update `update_issue` docstring: add same preview protocol
- [x] update `records_query` docstring: add note that for issue queries the assignee field is `implementer` (not `assignee`), with predicate example
- [x] run tests — must pass before next task

### Task 2: Delete agent files

- [x] delete `plugins/citeck/agents/citeck-explorer.md`
- [x] delete `plugins/citeck/agents/citeck-manager.md`
- [x] delete `plugins/citeck/agents/` directory (if empty)
- [x] run tests — must pass before next task

### Task 3: Update CLAUDE.md

- [x] remove agent definitions from Architecture section (citeck-explorer, citeck-manager)
- [x] remove Privilege Separation section about agents
- [x] remove agent entries from Agent definition format section
- [x] update Component relationships diagram — remove agent layer
- [x] run tests — must pass before next task

### Task 4: Update README.md (root)

- [x] remove Custom Agents table
- [x] remove Privilege Separation section
- [x] remove agent entries from Structure tree
- [x] run tests — must pass before next task

### Task 5: Update plugins/citeck/README.md

- [x] remove Custom Agents section (citeck-explorer, citeck-manager descriptions)
- [x] run tests — must pass before next task

### Task 6: Verify acceptance criteria

- [x] verify: main Claude process can call all MCP tools directly (no agents needed)
- [x] verify: no references to citeck-explorer or citeck-manager remain in codebase (except git history and completed plans)
- [x] run full test suite
- [x] run linter — all issues must be fixed

### Task 7: [Final] Update documentation

- [x] review all changes for consistency
- [x] ensure CLAUDE.md, README.md, and plugin README.md are aligned

## Technical Details

### Knowledge transfer: agent prompts → tool docstrings

| Agent instruction | Target location | Content |
|---|---|---|
| Mandatory preview protocol | `create_issue` + `update_issue` docstrings | "IMPORTANT: Always call with preview=true first. Show the FULL preview to the user. Get explicit confirmation before calling with preview=false." |
| `implementer` field name | `records_query` docstring | "Note: for issue queries, the assignee field is called `implementer` (not `assignee`). Example: `{\"t\": \"contains\", \"att\": \"implementer\", \"val\": [\"emodel/person@username\"]}`" |
| `assignee: "me"` resolution | Already in MCP server code | No change needed — enforced at runtime |
| Workspace auto-resolution | Already in MCP server code | No change needed — enforced at runtime |
| Project context workflow | Already in `create_issue` logic | No change needed — default project used automatically |

### What is NOT lost

These are enforced by MCP server code regardless of agents:
- `preview: true` as default parameter
- `assignee: "me"` → username resolution
- Workspace extraction from issue ID
- Project ref resolution from key
- Type suffix validation in `records_mutate`
- Dashboard link generation in `search_issues`, `create_issue`, `update_issue`

## Post-Completion

**Future consideration:**
- When Anthropic fixes plugin agent MCP access (issues #21560, #13605, #23374), agents can be re-added from git history
- New agents should be designed with updated MCP tool docstrings in mind (less duplication)
