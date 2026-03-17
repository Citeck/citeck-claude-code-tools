---
name: citeck-changes-to-task
description: "Create a Citeck Project Tracker issue from current git changes"
allowed-tools: Bash(git log *, git diff *, git branch --show-current, git branch -r, git merge-base *), Read, AskUserQuestion, mcp__citeck__list_projects, mcp__citeck__set_project_default, mcp__citeck__query_components, mcp__citeck__query_tags, mcp__citeck__create_issue
context: fork
---

# Citeck Changes to Task

Create a Citeck Project Tracker issue from current git changes. Analyzes the diff, generates a structured description, previews the issue, and creates it after confirmation.

## Prerequisites

Run `citeck:citeck-auth` first to configure your Citeck connection.

## Context

- Current branch: !`git branch --show-current`
- Remote branches: !`git branch -r`

## CRITICAL: Mandatory Dry-Run Protocol

**NEVER create an issue without showing a preview first.**

The flow MUST always be:
1. Build the issue parameters (type, summary, description)
2. Call `mcp__citeck__create_issue` with `preview: true` to generate a preview
3. Show the FULL preview to the user — NEVER summarize or paraphrase
4. Ask for explicit confirmation via AskUserQuestion
5. Only after confirmation call `mcp__citeck__create_issue` with `preview: false`

**Do NOT ask for generic confirmation — the user MUST see the preview before deciding.**

## Flow

### Step 1-4: Analyze changes and generate description

Read the shared task description guide and follow it:

```
Read file: ${CLAUDE_SKILL_DIR}/../_shared/task-description-guide.md
```

Follow Steps 1-4 from the guide to:
1. Determine the diff base
2. Get the changes via git log and git diff
3. Determine the task type (ask user to confirm)
4. Generate the title (English) and description (Russian)

### Step 5: Resolve project context

1. Call `mcp__citeck__list_projects()` to check for a default project and cached projects
2. If no default — call `mcp__citeck__list_projects(fetch: true)` and ask the user which project to use
3. Set the chosen project as default: `mcp__citeck__set_project_default(project: "PROJECT_KEY")`

### Step 6: Smart defaults

Automatically determine:

1. **Priority** from the issue context:
   - Security vulnerabilities, data loss, system crashes → `100_critical`
   - Broken core functionality, blocking issues → `200_high`
   - UI bugs, minor inconveniences, improvements → `300_medium`
   - Cosmetic issues, nice-to-haves → `400_low`

2. **Components** — call `mcp__citeck__query_components(project: "KEY")` and pick relevant ones. Omit if none match.

3. **Tags** — call `mcp__citeck__query_tags(project: "KEY")` and pick relevant ones. Omit if none match.

### Step 7: Preview

Call `mcp__citeck__create_issue` with `preview: true`:

```
mcp__citeck__create_issue(
  project: "<KEY>",
  type: "<task|story|bug>",
  summary: "<Title in English>",
  description: "<Description in Russian>",
  priority: "<priority>",
  assignee: "me",
  components: ["<ref>"],
  tags: ["<ref>"],
  preview: true
)
```

Show the FULL preview output to the user. Then ask via AskUserQuestion:

> **Create this issue in Citeck?**
> Options: "Yes, create", "Edit parameters", "Cancel"

**If "Edit parameters"**: ask what to change, re-run with `preview: true` and updated params, show the FULL preview again.

### Step 8: Create the issue

If confirmed, call the same tool with `preview: false`:

```
mcp__citeck__create_issue(
  project: "<KEY>",
  type: "<task|story|bug>",
  summary: "<Title in English>",
  description: "<Description in Russian>",
  priority: "<priority>",
  assignee: "me",
  components: ["<ref>"],
  tags: ["<ref>"],
  preview: false
)
```

Report the created issue key and link to the user.
