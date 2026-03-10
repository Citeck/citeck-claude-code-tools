---
name: citeck-changes-to-task-md
description: "Generate task.md file with structured task description from git changes"
allowed-tools: Bash(git log *, git diff *, git branch --show-current, git branch -r, git merge-base *), Read, Write, AskUserQuestion
context: fork
---

# Citeck Changes to Task (Markdown)

Generate a `task.md` file with a structured task description from current git changes. Does NOT create an issue in the tracker — only produces the markdown file.

## Context

- Current branch: !`git branch --show-current`
- Remote branches: !`git branch -r`

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

Create a file `task.md` in the project root. The output MUST be valid Markdown.

Format:

```
**Тип:** <Ошибка | История | Задача>

## <Title in English>

<Description in Russian, following the structure from the guide>
```

### Step 6: Report

Tell the user that `task.md` has been saved. Mention that they can use `/citeck:citeck-changes-to-task` to create an issue in Citeck Project Tracker directly from git changes.
