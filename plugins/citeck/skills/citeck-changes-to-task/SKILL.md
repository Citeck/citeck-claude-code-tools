---
name: citeck-changes-to-task
description: "Create a Citeck Project Tracker issue from current git changes"
---

## Client tools and paths

Use tools available in the current session by purpose; MCP names below are logical
Citeck tool names, not fixed client prefixes. Client permissions and sandbox rules apply.
Resolve `SKILL_DIR` to the absolute directory containing this loaded `SKILL.md`.
Resolve references from that directory and quote script paths, including paths with spaces.
These instructions do not create an isolated context automatically.
Claude Code: `/citeck:citeck-changes-to-task`; Codex: select `$citeck:citeck-changes-to-task`
from the skill picker, or request the skill by name in natural language.


# Citeck Changes to Task

Create a Citeck Project Tracker issue from current git changes. Analyzes the diff, generates a structured description, previews the issue, and creates it after confirmation.

## Prerequisites

Use the `citeck-auth` skill first to configure your Citeck connection.

Only inspect git changes and relevant files, query tracker metadata, preview and create
the confirmed issue. Do not modify source code, commit or push as part of this skill.

## Context

Run `git branch --show-current` and `git branch -r` explicitly before choosing the diff base.

## CRITICAL: Mandatory Dry-Run Protocol

**NEVER create an issue without showing a preview first.**

The flow MUST always be:
1. Build the issue parameters (type, summary, description)
2. Call `preview_issue` to generate a human-readable preview (read-only — it never creates anything)
3. Show the FULL preview `text` to the user — NEVER summarize or paraphrase
4. Ask for explicit confirmation using the available user-question mechanism
5. Only after confirmation call `create_issue` (which actually creates the issue)

**Do NOT ask for generic confirmation — the user MUST see the preview before deciding.**

## Flow

### Step 1-4: Analyze changes and generate description

Read the shared task description guide and follow it:

```
Read file: ${SKILL_DIR}/../_shared/task-description-guide.md
```

Follow Steps 1-4 from the guide to:
1. Determine the diff base
2. Get the changes via git log and git diff
3. Determine the task type (ask user to confirm)
4. Generate the title (English) and description (Russian)

### Step 5: Resolve tracker environment and project

Call `list_profiles` before any tracker operation. Resolve a concrete tracker profile
from the user request and applicable instructions, otherwise `ept_profile` or `active_profile`.
Record that profile's URL. Pass this same explicit `profile` to every tracker tool below,
including metadata queries, preview and creation. Never rely on a shared default after this step.
If the selected profile is missing, stop and ask the user to configure or select a profile.

1. Call `list_projects(profile: "<selected profile>")` to check for a default project and cached projects
2. If no default — call `list_projects(fetch: true, profile: "<selected profile>")` and ask the user which project to use
3. Set the chosen project as default: `set_project_default(project: "PROJECT_KEY", profile: "<selected profile>")`

### Step 6: Smart defaults

Automatically determine:

1. **Priority** from the issue context:
   - Security vulnerabilities, data loss, system crashes → `100_critical`
   - Broken core functionality, blocking issues → `200_high`
   - UI bugs, minor inconveniences, improvements → `300_medium`
   - Cosmetic issues, nice-to-haves → `400_low`

2. **Components** — call `query_components(project: "KEY", profile: "<selected profile>")` and pick relevant ones. Omit if none match.

3. **Tags** — call `query_tags(project: "KEY", profile: "<selected profile>")` and pick relevant ones. Omit if none match.

Resolve **assignee** and **fix_in_version** from the request or applicable user instructions.
Do not use `me` or a personal username as a universal default. If either is missing, ask the
user. Use `query_releases(project: "<KEY>", profile: "<selected profile>")` to validate the
chosen target release and pass its reference. An explicit choice of no release is allowed;
otherwise do not silently omit the release. Preserve the chosen assignee and release in
both preview and creation, including after parameter edits.

### Step 7: Preview

Call `preview_issue` (read-only):

```
preview_issue(
  project: "<KEY>",
  type: "<task|story|bug>",
  summary: "<Title in English>",
  description: "<Description in Russian>",
  priority: "<priority>",
  assignee: "<selected username>",
  fix_in_version: ["<selected release ref>"],
  profile: "<selected profile>",
  components: ["<ref>"],
  tags: ["<ref>"]
)
```

Require `ok: true` and verify the returned `profile` and `server` match the selected target.
If preview fails or differs from the selected target, stop without creating an issue.

Check creation access before writing. For a workspace in the preview's record, load
`emodel/workspace@<workspace>` through `records_query` with the selected `profile` and
attribute `isCurrentUserMember?bool`. Ordinary users must belong to that workspace
to create records there. `permissions._has.Write?bool` on the workspace itself does
not prove permission to create records inside it. If membership is false, stop and
select an accessible project; never probe access by attempting creation. System
authentication may have different rules, but do not assume that an ordinary user
has a system exception. If this check is unavailable, disclose that limitation.

Show the FULL preview `text` to the user (it already includes the target server/profile, resolved reference names, and the description rendered as readable text). Then ask using the available user-question mechanism:

> **Create this issue in Citeck? (server: <profile name / URL>)**
> Options: "Yes, create", "Edit parameters", "Cancel"

**If "Edit parameters"**: ask what to change, re-run `preview_issue` with updated params, show the FULL preview again.

### Step 8: Recheck environment and create the issue

After confirmation, call `list_profiles` again and locate the exact selected profile.
Compare its current URL with the preview's `server` (normalize trailing slashes only).
A change to another session's `active_profile` or `ept_profile` must not change the explicit
profile. If the selected profile was deleted, stop without falling back to another profile.
If its URL changed, or any issue parameter changed, generate a new preview, show its full
text, and obtain confirmation again before creation. Never create after cancellation.

Pass the confirmed preview’s `server` as `expected_server` to `create_issue`.
If creation reports a changed server, show a new preview and request confirmation again;
do not retry with the guard removed.

If the same profile, URL and parameters are still confirmed, call `create_issue` with the same parameters (no `preview` flag — this tool always creates):

```
create_issue(
  project: "<KEY>",
  type: "<task|story|bug>",
  summary: "<Title in English>",
  description: "<Description in Russian>",
  priority: "<priority>",
  assignee: "<selected username>",
  fix_in_version: ["<selected release ref>"],
  profile: "<selected profile>",
  expected_server: "<server URL from confirmed preview>",
  components: ["<ref>"],
  tags: ["<ref>"]
)
```

Report the created issue key and link to the user.
