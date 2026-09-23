---
name: citeck-planfact
description: "Use when the user asks for plan vs fact (план/факт/дельта, трудозатраты, списания vs оценки, перерасход, «сколько потратили против оценки») for a Citeck Project Tracker (EPT) project, epic or period."
allowed-tools: Bash(python3 */skills/citeck-planfact/scripts/planfact.py *), AskUserQuestion, mcp__citeck__list_profiles, mcp__citeck__reauthenticate
---

# Plan · Fact · Delta for an EPT project

One script call produces the whole report: estimates (plan), logged time (fact) and delta per epic, task and project, plus fact by user. Do not compute this by hand from `records_query` — the script pages through every issue of the project and does the arithmetic deterministically.

## Prerequisites

`/citeck:citeck-auth` done; the tracker is reached via `ept_profile` (falls back to the active profile). Check with `mcp__citeck__list_profiles` if unsure which profile hosts the tracker.

## Flow

### Step 1: Inputs

Required: **project key** (workspace, e.g. `EMTC`). Optional: **period** for the fact (`--from YYYY-MM-DD --to YYYY-MM-DD`, inclusive) and **epic** key to narrow the scope. If the user gave no project, ask once:

> **Какой проект (ключ) и за какой период считаем план/факт?**

### Step 2: Run

```
python3 ${CLAUDE_PLUGIN_ROOT}/skills/citeck-planfact/scripts/planfact.py EMTC --from 2026-08-01 --to 2026-08-31
```

Flags: `--epic EMTC-3` (one epic and its children), `--profile <name>`, `--json` (machine-readable, use it when you need to post-process).

### Step 3: Read the output

The script prints a markdown table (epic rows in bold, `↳` children, orphan tasks under «Без эпика», «Итого»), the totals converted by the norms and the line «Факт без оценки». Relay it to the user as is, then add 2–4 sentences of interpretation, in this order:

1. **Overruns** — rows with plan > 0 and negative delta. Only these are real overruns.
2. **Unestimated work** — rows with plan 0 and fact > 0 (the «Факт без оценки» line sums them). Report them as «оценки нет», never as overrun.
3. **Coarse plans** — epics marked `[своя]`: no child has an estimate, the epic number is a top-down guess.

For a big project (hundreds of rows) save the output to a file and `grep` the negative-delta rows instead of reading the whole table; `--json` is there for anything more elaborate.

## Rules baked into the script

- **Plan** = `estimatedWorks` parsed like the platform (`1w 2d 3h 30m`; 1d = 8h, 1w = 5d).
- **Epic plan** = sum of children estimates when at least one child is estimated (`[дети]`), otherwise the epic's own estimate (`[своя]`). The platform itself does no aggregation, so summing epic + children naively double-counts — the script avoids that.
- **Fact** = sum of `durationInMinutes` of time-tracking records under the issue; with a period only records whose `startDate` falls inside it. Plan is never filtered by period.
- **Delta** = plan − fact. Positive = under the estimate, negative = overrun.
- **Norms**: 8 h/day, 5 d/week, 4 w/month (160 h). Applied to both plan and fact in the «по нормам» lines.

## Edge cases

- **Authentication error** in stderr → run `mcp__citeck__reauthenticate`, then rerun the script.
- **0 issues** → wrong project key or the profile does not host the tracker; show `list_profiles` and ask.
- **Task with both `epicLink` and own estimate while the epic has none** → counted via children rule, expected.
- Estimates are stored only on issues; a Jira-style «epic estimate rolls up» does not exist here — say so if the user asks why the epic number differs from its card.
