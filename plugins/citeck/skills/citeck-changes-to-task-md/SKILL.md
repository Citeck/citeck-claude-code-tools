---
name: citeck-changes-to-task-md
description: "Generate task.md file with structured task description from git changes"
---

## Client tools and paths

Use tools available in the current session by purpose; MCP names below are logical
Citeck tool names, not fixed client prefixes. Client permissions and sandbox rules apply.
Resolve `SKILL_DIR` to the absolute directory containing this loaded `SKILL.md`.
Resolve references from that directory and quote script paths, including paths with spaces.
These instructions do not create an isolated context automatically.
Claude Code: `/citeck:citeck-changes-to-task-md`; Codex: select `$citeck:citeck-changes-to-task-md`
from the skill picker, or request the skill by name in natural language.


# Citeck Changes to Task (Markdown)

Generate a `task.md` file with a structured task description from current git changes. Does NOT create an issue in the tracker — only produces the markdown file.

## Context

Run `git branch --show-current` and `git branch -r` explicitly before choosing the diff base.

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

### Step 5: Write task.md

Create a file `task.md` in the project root. If it already exists, inspect it and ask before replacing user content. The output MUST be valid Markdown.

Format:

```
**Тип:** <Ошибка | История | Задача>

## <Title in English>

<Description in Russian, following the structure from the guide>
```

### Step 6: Report

Tell the user that `task.md` has been saved. Mention that they can use the `citeck-changes-to-task` skill to create an issue in Citeck Project Tracker directly from git changes.
