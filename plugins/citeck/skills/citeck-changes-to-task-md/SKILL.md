---
name: citeck-changes-to-task-md
description: "Generate task.md file with structured task description from git changes"
allowed-tools: >-
  Bash(git branch --show-current),
  Bash(git branch -r),
  Bash(git merge-base *),
  Bash(git log *),
  Bash(git diff *),
  Read,
  Write,
  AskUserQuestion
---

## Client compatibility

Shared by Claude Code and Codex.
- Skill directory: `${CLAUDE_SKILL_DIR}`. Claude Code substitutes it; if it appears unexpanded,
  use the absolute directory containing this `SKILL.md`.
- User-question mechanism: `AskUserQuestion` in Claude Code; elsewhere the client's question
  tool, or ask in chat and wait for the answer.

# Citeck Changes to Task (Markdown)

Generate a `task.md` file with a structured task description from current git changes. Does NOT create an issue in the tracker — only produces the markdown file.

## Context

Run `git branch --show-current` and `git branch -r` explicitly before choosing the diff base.

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
