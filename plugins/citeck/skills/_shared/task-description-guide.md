# Task Description Guide

Shared rules for generating task descriptions from git changes.

## Step 1: Determine the diff base

Run `git branch --show-current` to get the current branch name, then:

- If the current branch is `develop`, `master`, or `main`: the base is `origin/<current-branch>` (remote tracking). This shows local unpushed changes.
- If the current branch is any other branch: run `git merge-base origin/develop HEAD`, `git merge-base origin/main HEAD`, `git merge-base origin/master HEAD` (whichever remote branches exist) and pick the one closest to HEAD (most recent merge-base). That merge-base commit is the diff base.

## Step 2: Get the changes

Run these git commands using the base determined in Step 1:

- `git log <base>..HEAD --oneline` for the commit history
- `git diff --stat <base>..HEAD` for the list of changed files
- `git diff <base>..HEAD -- <path>` for the content of relevant files; read the full
  `git diff <base>..HEAD` only when it is small. This keeps the session context compact.

Read and understand all the changes:
- What files were modified, added, or deleted
- What is the purpose of the changes (bug fix, new feature, refactoring, configuration change, etc.)
- What is the functional impact from a QA/tester perspective

## Step 3: Determine the task type

Analyze the changes and determine the task type:

- **Bug** (Ошибка) -- commits contain fix/bugfix/hotfix keywords, or changes fix incorrect behavior (condition fixes, edge-case handling, null-checks, error corrections)
- **Story** (История) -- new files, components, API endpoints, significant new functionality or user-facing capabilities
- **Task** (Задача) -- refactoring, dependency updates, configuration changes, tech debt, migrations, build/CI changes, code cleanup

Ask the user to confirm or correct the type using the available user-question mechanism:
- Set the determined type as the first option with "(Recommended)" suffix
- List the other two types as alternatives

Example:
> **Determined task type: Bug**
> Options: "Bug (Recommended)", "Story", "Task"

Proceed with the confirmed type.

## Step 4: Generate title and description

Rules:
- **Title**: concise, in English, imperative mood (e.g., "Add validation for signal event data model values", "Fix NPE in process timer execution"). Should be suitable as a task summary.
- **Description**: in Russian, written for a QA tester. Keep it brief and clear. The structure depends on the task type (see below). The format (Markdown or Lexical HTML) is set by the calling skill (see "Formatting rules").
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
- **Что изменено**: OMIT this section if the description already covers what was done — avoid duplication.
- **Риски и затронутые области**: OMIT this section if changes are isolated and obviously safe (dependency bump, config tweak, renaming, etc.). Include only when there is a real risk worth mentioning.
- **Шаги воспроизведения** (bugs only): write concrete, reproducible steps. Use numbered list. Include expected vs actual results.

### Formatting rules

The calling skill sets the output format: Markdown or Lexical HTML. Use only the column for
that format. The templates above show the structure in Markdown notation.

| Element | Markdown | Lexical HTML |
|---|---|---|
| Paragraph | text, separated by a blank line | `<p>text</p>` |
| Line that stands on its own in a template (**Ожидаемый результат:**, **Фактический результат:**, each of *Given*/*When*/*Then*) | own line, as in the template | own `<p>…</p>` |
| Section header | `#### Header` | `<h3>Header</h3>` |
| Bullet list | `- item` | `<ul><li>item</li></ul>` |
| Numbered list (Steps to Reproduce) | `1. item` | `<ol><li>item</li></ol>` |
| Bold | `**text**` | `<b>text</b>` |
| Italic | `*text*` | `<i>text</i>` |
| Inline code (variable names, expressions, attribute paths, etc.) | `` `code` `` | `<code>code</code>` |

- Markdown: separate sections with blank lines for readability.
- Lexical HTML: use only the tags from the table, without attributes. Escape `<`, `>`, `&` in
  text as `&lt;`, `&gt;`, `&amp;`. Do not mix in Markdown: it shows literally.
- Use inline code only for meaningful expressions and identifiers. Do NOT wrap individual characters or short punctuation in inline code.

### Review before finalizing

Before using the generated text, carefully review:

1. **Structure completeness** -- verify that all required sections for the determined task type are present.
2. **Code and expression validity** -- every code example, expression, or identifier mentioned in the description must be syntactically valid and make sense in context.
3. **Grammar and spelling** -- proofread the Russian text for grammatical errors, typos, misused cases, missing prepositions, and awkward phrasing.
4. **Format correctness** -- ensure valid syntax throughout in the format the calling skill requires (see "Formatting rules").

Fix any issues found before proceeding.

## Type Mapping

| Type name | CLI type arg | Issue type ID |
|---|---|---|
| Ошибка | `bug` | `ept-issue-bug` |
| История | `story` | `ept-issue-story` |
| Задача | `task` | `ept-issue-task` |
