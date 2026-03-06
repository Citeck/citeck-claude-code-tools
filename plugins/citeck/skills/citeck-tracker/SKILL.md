---
name: citeck-tracker
description: "Manage issues in Citeck Project Tracker — create, update, search tasks across projects"
allowed-tools: Bash(python3 */skills/citeck-tracker/scripts/manage_projects.py *, python3 */skills/citeck-tracker/scripts/query_issues.py *, python3 */skills/citeck-tracker/scripts/query_sprints.py *, python3 */skills/citeck-tracker/scripts/query_components.py *, python3 */skills/citeck-tracker/scripts/query_tags.py *, python3 */skills/citeck-tracker/scripts/query_releases.py *, python3 */skills/citeck-tracker/scripts/create_issue.py *, python3 */skills/citeck-tracker/scripts/update_issue.py *), AskUserQuestion
---

# Citeck Project Tracker

Manage issues in Citeck ECOS Project Tracker — create, update, search tasks across projects.

## Prerequisites

Run `citeck:citeck-auth` first to configure your Citeck connection (URL, credentials).

## MANDATORY: Project Context Resolution

**You MUST determine the project before ANY tracker operation.** Follow this pipeline strictly:

### Step 1: Check saved default
Run `python3 ${CLAUDE_SKILL_DIR}/scripts/manage_projects.py --list` to check if a default project is already saved.

### Step 2a: Default exists → use it
If `default_project` is set, use it automatically. No need to ask the user.

### Step 2b: No default → ask user
If `default_project` is null:
1. Run `python3 ${CLAUDE_SKILL_DIR}/scripts/manage_projects.py --fetch` to get available projects from Citeck
2. Show the list to the user via AskUserQuestion: "Какой проект использовать? Вот доступные: ..." and ask which to set as default
3. Save their choice: `python3 ${CLAUDE_SKILL_DIR}/scripts/manage_projects.py --set-default PROJECT_KEY`

### Step 3: User mentions a different project
If the user explicitly names a project different from the default — use it for this operation and add it to the saved list:
`python3 ${CLAUDE_SKILL_DIR}/scripts/manage_projects.py --add PROJECT_KEY`

All `--project` arguments in scripts fall back to the saved default when omitted.

## IMPORTANT: Raw JSON Query Rules

When constructing raw `--json` queries, use the correct Records API attribute names:

| CLI arg       | Records API attribute | Notes                                      |
|---------------|----------------------|--------------------------------------------|
| `--assignee`  | `implementer`        | NOT `assignee`. Array field, use `contains` |
| `--status`    | `_status`            | With underscore prefix                     |
| `--type`      | `_type`              | With underscore prefix                     |

**NEVER use `assignee` as an attribute in raw JSON queries — the correct attribute is `implementer`.**

Example raw JSON query for issues by implementer:
```json
{"t": "contains", "att": "implementer", "val": ["emodel/person@username"]}
```

## IMPORTANT: Task Links in Responses

When showing task IDs (e.g., COREDEV-26) in responses to the user, ALWAYS format them as clickable links. The URL pattern is:

```
{citeck_base_url}/v2/dashboard?recordRef=emodel/ept-issue@{TASK_ID}
```

To get the base URL, read it from the saved credentials. Example link format in responses:

```
[COREDEV-26]({base_url}/v2/dashboard?recordRef=emodel/ept-issue@COREDEV-26)
```

Always use this format for every task ID mentioned in your response.

## Operations

| Script                | Purpose                          | Safety                                    |
|-----------------------|----------------------------------|-------------------------------------------|
| `manage_projects.py`  | Manage saved project preferences | Read/write config, safe                   |
| `query_issues.py`     | Search/list issues               | Read-only, safe                           |
| `query_sprints.py`    | List sprints                     | Read-only, safe                           |
| `query_components.py` | List components                  | Read-only, safe                           |
| `query_tags.py`       | List tags                        | Read-only, safe                           |
| `query_releases.py`   | List releases                    | Read-only, safe                           |
| `create_issue.py`     | Create task/story/bug/epic       | **Creates data — requires confirmation**  |
| `update_issue.py`     | Update issue attributes/status   | **Modifies data — requires confirmation** |

## CRITICAL: Data Modification Safety

**Create and Update operations modify real data.** Before executing ANY `create_issue.py` or `update_issue.py`:

1. First run with `--dry-run` to generate a preview
2. Show the FULL preview table to the user — NEVER summarize or paraphrase the dry-run output
3. **Ask the user for explicit confirmation** via AskUserQuestion
4. Only then run WITHOUT `--dry-run` to apply changes

**If the user requests corrections:** re-run `--dry-run` with updated parameters and show the FULL preview table again. The user must always see the complete table before confirming, not just a text summary of what changed.

Query operations are read-only and safe to execute without confirmation.

## Issue Types

| Type    | ID                 |
|---------|--------------------|
| Task    | `ept-issue-task`   |
| Story   | `ept-issue-story`  |
| Bug     | `ept-issue-bug`    |
| Epic    | `ept-issue-epic`   |

## Priority Values

| Priority | Value        |
|----------|-------------|
| Urgent   | `100_urgent` |
| High     | `200_high`   |
| Medium   | `300_medium` |
| Low      | `400_low`    |

## Statuses

Common statuses: `backlog`, `to-do`, `in-progress`, `review`, `done`

## 0. Manage Projects

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/manage_projects.py --list
python3 ${CLAUDE_SKILL_DIR}/scripts/manage_projects.py --fetch
python3 ${CLAUDE_SKILL_DIR}/scripts/manage_projects.py --add COREDEV
python3 ${CLAUDE_SKILL_DIR}/scripts/manage_projects.py --remove COREDEV
python3 ${CLAUDE_SKILL_DIR}/scripts/manage_projects.py --set-default COREDEV
```

## 1. Search Issues

### Structured query (CLI args)

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/query_issues.py [--project EPT] [--status in-progress] [--assignee me] [--type task] [--sprint REF] [--limit 20] [--sort _created] [--asc]
```

Parameters:
- `--project` — Workspace/project key (optional; uses default if not set)
- `--assignee` — Username or `me` (resolves to current authenticated user)
- `--status` — Filter by status (e.g., `in-progress`, `done`, `backlog`)
- `--type` — Filter by type: `task`, `story`, `bug`, `epic`
- `--sprint` — Filter by sprint (full ref, e.g., `emodel/ept-sprint@UUID`)
- `--sort` — Sort attribute (default: `_created`)
- `--asc` — Sort ascending (default: descending)
- `--limit` — Max results (default: 20)

Returns formatted table of matching issues.

### Load record attributes by ID

Load all attributes of a specific record using `?json`:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/query_issues.py --record "emodel/ept-issue@EPT-123"
```

Load specific attributes:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/query_issues.py --record "emodel/ept-issue@EPT-123" --attrs "summary?str,priority?str,_status?str"
```

The `?json` attribute returns ALL attributes of a record as a JSON object — useful for exploring record structure and discovering available fields.

### Raw JSON query

Send an arbitrary Records API query body:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/query_issues.py --json '{"records":["emodel/project@UUID"],"attributes":["?json"],"version":1}'
```

This bypasses all other arguments and sends the JSON directly to the `/gateway/api/records/query` endpoint. Useful for advanced queries or debugging.

## 2. Query Sprints

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/query_sprints.py [--project COREDEV] [--status new|in-progress|completed] [--limit 20] [--asc]
```

Returns formatted table with sprint name, status, start/end dates.

## 3. Query Components

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/query_components.py [--project COREDEV] [--limit 50] [--asc]
```

Returns formatted table with component name, creator.

## 4. Query Tags

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/query_tags.py [--project COREDEV] [--limit 50] [--asc]
```

Returns formatted table with tag name, creator.

## 5. Query Releases

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/query_releases.py [--project COREDEV] [--status new|in-progress|completed] [--limit 20] [--asc]
```

Returns formatted table with release name, status, start/release dates, implementer.

## 6. [CREATE] Create Issue

**Language rule:** Summary (title) MUST always be in English. Description MUST be in Russian.

**Requires user confirmation before execution.**

### Smart defaults

When creating an issue, you SHOULD automatically:

1. **Determine priority** from the issue description context:
   - Security vulnerabilities, data loss, system crashes → `100_urgent`
   - Broken core functionality, blocking issues → `200_high`
   - UI bugs, minor inconveniences, improvements → `300_medium`
   - Cosmetic issues, nice-to-haves → `400_low`

2. **Match components** — run `python3 ${CLAUDE_SKILL_DIR}/scripts/query_components.py` to get the list, then pick the most relevant component(s) based on the issue description. If no component clearly matches, omit it.

3. **Match tags** — run `python3 ${CLAUDE_SKILL_DIR}/scripts/query_tags.py` to get the list, then pick relevant tag(s). If no tag clearly matches, omit it.

### Assignee resolution

`--assignee me` automatically resolves to the current authenticated user's username via JWT token.

### Usage

Preview first (dry-run):
```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/create_issue.py --project EPT --type task --summary "Fix login bug" --description "Login fails on mobile" --dry-run
```

Then create:
```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/create_issue.py --project EPT --type task --summary "Fix login bug" --description "Login fails on mobile" [--priority 300_medium] [--assignee me] [--sprint ref] [--component ref] [--tags ref]
```

- `--project` is optional if default project is set.
- `--component` can be repeated for multiple components.
- `--tags` can be repeated for multiple tags.
- `--assignee me` resolves to the authenticated user.

## 7. [UPDATE] Update Issue

**Requires user confirmation before execution.**

Preview first (dry-run):
```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/update_issue.py --issue EPT-123 --status in-progress --dry-run
```

Then apply:
```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/update_issue.py --issue EPT-123 --status in-progress [--assignee person/username] [--priority 200_high] [--summary "Updated title"]
```

## Workflow Example

1. Check project context: `python3 ${CLAUDE_SKILL_DIR}/scripts/manage_projects.py --list`
2. Set default project: `python3 ${CLAUDE_SKILL_DIR}/scripts/manage_projects.py --set-default COREDEV`
3. Query my issues: `python3 ${CLAUDE_SKILL_DIR}/scripts/query_issues.py --assignee me`
4. Query sprints: `python3 ${CLAUDE_SKILL_DIR}/scripts/query_sprints.py`
5. Query by status: `python3 ${CLAUDE_SKILL_DIR}/scripts/query_issues.py --status to-do`
6. Create issue: preview with `--dry-run`, confirm, then create
7. Update status: preview with `--dry-run`, confirm, then update
