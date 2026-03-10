# Task Description Guide

Shared rules for generating task descriptions from git changes.

## Step 1: Determine the diff base

Run `git branch --show-current` to get the current branch name, then:

- If the current branch is `develop`, `master`, or `main`: the base is `origin/<current-branch>` (remote tracking). This shows local unpushed changes.
- If the current branch is any other branch: run `git merge-base origin/develop HEAD`, `git merge-base origin/main HEAD`, `git merge-base origin/master HEAD` (whichever remote branches exist) and pick the one closest to HEAD (most recent merge-base). That merge-base commit is the diff base.

## Step 2: Get the changes

Run these git commands using the base determined in Step 1:

- `git log <base>..HEAD --oneline` for the commit history
- `git diff <base>..HEAD` for the full content diff

Read and understand all the changes:
- What files were modified, added, or deleted
- What is the purpose of the changes (bug fix, new feature, refactoring, configuration change, etc.)
- What is the functional impact from a QA/tester perspective

## Step 3: Determine the task type

Analyze the changes and determine the task type:

- **Bug** (Ошибка) -- commits contain fix/bugfix/hotfix keywords, or changes fix incorrect behavior (condition fixes, edge-case handling, null-checks, error corrections)
- **Story** (История) -- new files, components, API endpoints, significant new functionality or user-facing capabilities
- **Task** (Задача) -- refactoring, dependency updates, configuration changes, tech debt, migrations, build/CI changes, code cleanup

Ask the user to confirm or correct the type using `AskUserQuestion`:
- Set the determined type as the first option with "(Recommended)" suffix
- List the other two types as alternatives

Example:
> **Determined task type: Bug**
> Options: "Bug (Recommended)", "Story", "Task"

Proceed with the confirmed type.

## Step 4: Generate title and description

Rules:
- **Title**: concise, in English, imperative mood (e.g., "Add validation for signal event data model values", "Fix NPE in process timer execution"). Should be suitable as a task summary.
- **Description**: in Russian, written for a QA tester. Keep it brief and clear. The structure depends on the task type (see below).
- Write the description in the **present tense** (e.g., "выводится слитно", "затрудняет восприятие"), NOT past tense.
- Do NOT include raw diffs or file listings in the description. Summarize at the functional level.

### Description structure by task type

**For "Ошибка" (Bug):**

```markdown
<Bug description -- what is broken, under what conditions, how it manifests>

#### Шаги воспроизведения

1. Step 1
2. Step 2
3. Step 3

**Ожидаемый результат:** <what should happen>
**Фактический результат:** <what actually happens>

#### Что изменено

- <functional summary of changes>

#### Критерии приёмки

*Given* <precondition>

*When* <action>

*Then* <expected outcome>

- <additional checklist item>

#### Риски и затронутые области

- <affected module/component> -- <potential impact>
```

**For "История" (Story):**

```markdown
<Rationale -- why this is needed, what problem it solves, what it gives the user>

#### Что изменено

- <functional summary of changes>

#### Критерии приёмки

*Given* <precondition>

*When* <action>

*Then* <expected outcome>

- <additional checklist item>

#### Риски и затронутые области

- <affected module/component> -- <potential impact>
```

**For "Задача" (Task):**

```markdown
<What was done and why -- technical rationale>

#### Что изменено

- <functional summary of changes>

#### Критерии приёмки

- Сборка проходит без ошибок
- <specific non-regression checks>
- <other verifiable criteria>

#### Риски и затронутые области

- <affected module/component> -- <potential impact>
```

### Guidelines for each section

- **Критерии приёмки**: use *Given*/*When*/*Then* (italic) for key user scenarios. Each keyword (*Given*, *When*, *Then*) MUST be separated by a blank line for readability. Use bullet list items for smaller checks. For "Задача" type, checklist format is preferred over Given/When/Then.
- **Риски и затронутые области**: list the modules, components, or areas of the system that are affected by the changes. Mention what could break or regress. If the changes are isolated and low-risk, say so explicitly.
- **Шаги воспроизведения** (bugs only): write concrete, reproducible steps. Use numbered list. Include expected vs actual results.

### Markdown formatting rules

The output MUST be valid Markdown:

- Use `**text**` for bold
- Use `*text*` for italic
- Use `` `code` `` for inline code (variable names, expressions, attribute paths, etc.)
- Use `####` for section headers
- Use `- item` for bullet lists
- Use `1. item` for numbered lists (Steps to Reproduce)
- Separate sections with blank lines for readability
- Use inline code only for meaningful expressions and identifiers. Do NOT wrap individual characters or short punctuation in backticks.

### Review before finalizing

Before using the generated text, carefully review:

1. **Structure completeness** -- verify that all required sections for the determined task type are present.
2. **Code and expression validity** -- every code example, expression, or identifier mentioned in the description must be syntactically valid and make sense in context.
3. **Grammar and spelling** -- proofread the Russian text for grammatical errors, typos, misused cases, missing prepositions, and awkward phrasing.
4. **Markdown correctness** -- ensure valid Markdown syntax throughout.

Fix any issues found before proceeding.

## Type Mapping

| Type name | CLI type arg | Issue type ID |
|---|---|---|
| Ошибка | `bug` | `ept-issue-bug` |
| История | `story` | `ept-issue-story` |
| Задача | `task` | `ept-issue-task` |
