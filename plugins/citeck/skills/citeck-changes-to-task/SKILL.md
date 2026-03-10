---
name: citeck-changes-to-task
description: "Create a Citeck Project Tracker issue from current git changes"
allowed-tools: Bash(git log *, git diff *, git branch --show-current, git branch -r, git merge-base *, python3 */skills/citeck-tracker/scripts/create_issue.py *, python3 */skills/citeck-tracker/scripts/manage_projects.py *, python3 */skills/citeck-tracker/scripts/query_components.py *, python3 */skills/citeck-tracker/scripts/query_tags.py *), Read, AskUserQuestion
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

**NEVER create an issue without showing a dry-run preview first.**

The flow MUST always be:
1. Build the issue parameters (type, summary, description)
2. Run `create_issue.py --dry-run` to generate a preview
3. Show the FULL preview table to the user — NEVER summarize or paraphrase
4. Ask for explicit confirmation via AskUserQuestion
5. Only after confirmation run WITHOUT `--dry-run`

**Do NOT ask for generic Bash execution confirmation — the user MUST see the preview table before deciding.**

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

1. Run `python3 ${CLAUDE_SKILL_DIR}/../citeck-tracker/scripts/manage_projects.py --list` to check for a default project
2. If no default — run `python3 ${CLAUDE_SKILL_DIR}/../citeck-tracker/scripts/manage_projects.py --fetch` and ask the user which project to use
3. Set the chosen project as default: `python3 ${CLAUDE_SKILL_DIR}/../citeck-tracker/scripts/manage_projects.py --set-default PROJECT_KEY`

### Step 6: Smart defaults

Automatically determine:

1. **Priority** from the issue context:
   - Security vulnerabilities, data loss, system crashes → `100_urgent`
   - Broken core functionality, blocking issues → `200_high`
   - UI bugs, minor inconveniences, improvements → `300_medium`
   - Cosmetic issues, nice-to-haves → `400_low`

2. **Components** — run `python3 ${CLAUDE_SKILL_DIR}/../citeck-tracker/scripts/query_components.py` and pick relevant ones. Omit if none match.

3. **Tags** — run `python3 ${CLAUDE_SKILL_DIR}/../citeck-tracker/scripts/query_tags.py` and pick relevant ones. Omit if none match.

### Step 7: Dry-run preview

Run `create_issue.py` with `--dry-run` to preview the issue:

```bash
python3 ${CLAUDE_SKILL_DIR}/../citeck-tracker/scripts/create_issue.py \
  --project <KEY> \
  --type <task|story|bug> \
  --summary "<Title in English>" \
  --description "<Description in Russian>" \
  --priority <priority> \
  [--assignee me] \
  [--component <ref>] \
  [--tags <ref>] \
  --dry-run
```

Show the FULL preview output to the user. Then ask via AskUserQuestion:

> **Create this issue in Citeck?**
> Options: "Yes, create", "Edit parameters", "Cancel"

**If "Edit parameters"**: ask what to change, re-run `--dry-run` with updated params, show the FULL preview table again.

### Step 8: Create the issue

If confirmed, run the same command WITHOUT `--dry-run`:

```bash
python3 ${CLAUDE_SKILL_DIR}/../citeck-tracker/scripts/create_issue.py \
  --project <KEY> \
  --type <task|story|bug> \
  --summary "<Title in English>" \
  --description "<Description in Russian>" \
  --priority <priority> \
  [--assignee me] \
  [--component <ref>] \
  [--tags <ref>]
```

Report the created issue key and link to the user.
