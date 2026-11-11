---
name: citeck-app-from-spec
description: "EXPERIMENTAL (stage-1 prototype; the result is checked through Records API, a working UI is not guaranteed). Build a new Citeck ECOS application from a requirements document (ТЗ): plan, write ecos-apps artifact files, check BPMN with the platform, deploy into one workspace, walk the main scenario on the stand, fix and redeploy in a loop, and report requirement by requirement. Use when asked to create or generate an application, business app or process automation from a spec on a Citeck stand."
allowed-tools: >-
  AskUserQuestion,
  Read,
  Write,
  Edit,
  Glob,
  Grep,
  Bash,
  mcp__plugin_citeck_citeck__bpmn_validate,
  mcp__plugin_citeck_citeck__bpmn_layout,
  mcp__plugin_citeck_citeck__deploy_app,
  mcp__plugin_citeck_citeck__records_query,
  mcp__plugin_citeck_citeck__records_mutate,
  mcp__plugin_citeck_citeck__search_docs,
  mcp__plugin_citeck_citeck__list_profiles
---

## Status: experimental

This skill is a stage-1 prototype and is not developed further as an application generator. In the two measured runs
on a CRM requirements document the main scenario worked through Records API in one of them, and in neither did the
application work in the browser: the create form had no save button and the task showed no outcome buttons. Tell the
user this before starting, and always check the create form and the first task in the browser before reporting the
application as working. The tools `deploy_app`, `bpmn_validate` and `bpmn_layout` and the reference files are stable
and can be used on their own.

## Client compatibility

In Pi, Citeck MCP tools are normally deferred: discover `mcp__citeck__<tool>`
with `tool_search` or the available codemode discovery before calling them. This skill uses:
`bpmn_validate`, `bpmn_layout`, `deploy_app`, `records_query`, `records_mutate`, `search_docs`,
`list_profiles`. Treat an application result with `ok: false` as failure even without MCP `isError`.

Shared by Claude Code, Codex and Pi. In Pi invoke as `/skill:citeck-app-from-spec`.
- Skill directory: `${CLAUDE_SKILL_DIR}`. Claude Code substitutes it; if it appears unexpanded,
  use the absolute directory containing this `SKILL.md`.
- MCP tools are named without the client prefix.
- User-question mechanism: `AskUserQuestion` in Claude Code; elsewhere the client's question
  tool, or ask in chat and wait for the answer.

# Application from a requirements document

You turn a ТЗ into a working application on a Citeck stand: artifacts are **files** in an `ecos-apps`
application directory under git; the stand gets them only through `deploy_app`.

## Before you start

Read these once, fully, before planning:
- `${CLAUDE_SKILL_DIR}/references/ecos-apps-layout.md` — directory layout, workspace scoping, deploy cycle;
- `${CLAUDE_SKILL_DIR}/references/platform-traps.md` — platform facts that broke earlier generated apps;
- `${CLAUDE_SKILL_DIR}/references/stand-actions.md` — how to create records, find and complete process
  tasks, and check the UI with the browser on the stand.
Read a schema from `${CLAUDE_SKILL_DIR}/references/schemas/` when you write an artifact of that kind.

## Sources of platform knowledge

Do not write an artifact kind from memory. Before planning, and again before writing each kind,
look at how the platform and its own applications do it. The operator gives a directory of read-only
source clones (`CITECK_SOURCES_DIR`; ask if it is not set). Use what is there:
- **Documentation:** `search_docs` (query in Russian) when the tool answers; otherwise, and for the
  exact text, `$CITECK_SOURCES_DIR/ecos-docs` (rst/md) — search it with grep, read only the hits.
- **Reference applications:** `$CITECK_SOURCES_DIR/ecos-contracts`, other `ecos-*` applications with
  `src/main/resources/app/artifacts/` — real artifacts of every kind; copy their structure, not their ids.
- **Built-in types to reuse instead of creating your own:** `$CITECK_SOURCES_DIR/ecos-datalist`
  (`src/main/resources/app/artifacts/model/type/`: counterparty, legal entity, currency, units, VAT, ...).
  Refer to them as `emodel/type@<id>`; never copy them into the application.
- **Artifact schemas:** `$CITECK_SOURCES_DIR/ecos-idea-plugin/src/main/resources/citeck/artifacts/<kind>/` —
  the validation schemas the IDE plugin uses; check every artifact file against its schema before deploying.
- **Platform services:** the microservices next to them (`ecos-model`, `uiserv`, `ecos-process`,
  `ecos-apps`, ...) when a schema or the docs do not answer how a field behaves.
Search only where artifacts and code live: `src/main/resources` and `src/main/java` (or `src/main/kotlin`)
of the repositories you need — never the whole directory: `node_modules`, `target` and `build` make a
recursive search time out.
Write down in `PLAN.md` which sources you used for each artifact kind.

The operator sets the session up (ask if something is missing, do not guess):
- the generation workspace id (`CITECK_GEN_WORKSPACE`), the profiles (`list_profiles`) and which user
  plays which role of the ТЗ. Never let one user play two roles you check (an author who is also the
  specialist cannot show that the specialist sees what the author does not); ask for another profile;
- the run limit (time and tokens; default 2 hours). When it is reached, stop and write the report.

## Rules

- Write artifacts only as files and deploy only with `deploy_app`. Never create or change types,
  forms, journals, processes, permissions, menus, applications or workspaces with `records_mutate`;
  in generation mode it refuses, and a bypass by other means voids the run.
- Touch nothing outside the generation workspace. Your types: `emodel/type@CURRENT_WS:<id>` in files.
  An artifact patch sets `workspace: <generation workspace>`; a patch names only records and
  artifacts of this workspace. `deploy_app` refuses the rest.
- Never write the BPMN diagram (`bpmndi:*`). Keep the semantic process in `process-src/<id>.bpmn.xml`
  (outside `artifacts/`, not uploaded) and edit only that file; `bpmn_validate` it, then
  `bpmn_layout(file_path=process-src/<id>.bpmn.xml, output_path=artifacts/process/bpmn/<id>.bpmn.xml)`.
  The laid-out file is rewritten by the platform (attribute order, escaping): never edit it by hand.
- A role that several people share and any of them takes («a purchasing specialist takes the request»)
  is a type role with static `assignees` (users or existing groups), not a field one person fills in.
  Do not create groups: they are global.
- A tool outcome `service_unavailable` is not a defect of your files: do not regenerate because of it.
- Act as a user by passing `profile` to `records_query` / `records_mutate`; do not switch the active
  profile. `deploy_app` always runs under the operator's deploy profile.
- Never claim what you did not check on the stand. Unfinished work is stated as unfinished.

## Flow

### 1. Plan
Read the ТЗ fully. Write `PLAN.md` in the application directory: the artifacts you will create
(kind, id, purpose) and, for every requirement of the ТЗ, which artifact covers it. Free form.
If your shell can run a separate agent, have one review the plan against the ТЗ and the sources above
(missing requirements, own types where a built-in one exists, artifacts of the wrong kind) and fix it.
Show the plan to the human and wait for confirmation. On «cancel» stop: nothing is deployed.

### 2. Write
Create the directory (`git init`, `meta.json`, `artifacts/...`) and write the artifacts.

Before the first deploy check every artifact file against its schema (`ecos-idea-plugin`), and, if
your shell can run separate agents, have one review the artifacts against the plan and the schemas.

### 3. Check processes
For every process: `bpmn_validate(process-src/<id>.bpmn.xml)` until `valid`, then
`bpmn_layout(file_path=process-src/<id>.bpmn.xml, output_path=artifacts/process/bpmn/<id>.bpmn.xml)` once. `layout_rejected` → back to `bpmn_validate`;
`layout_failed` / `unknown_after_timeout` → the platform may still be computing: do not call `bpmn_layout` for two
minutes, then call it once; if it is unknown again, report the process without a diagram.
Keep each process under 100 000 characters after layout (see the traps reference).

### 4. Deploy
`deploy_app(app_dir, members=[<participant user>])`. Read `outcome` and `ok`:
- `deployed` with `ok: true` — every changed artifact is deployed and nothing of the app is failed;
- `deployed_with_errors` — fix each artifact in `changed` with `DEPLOY_FAILED` using its `errors`
  (look the error up in the sources above when its cause is not obvious);
  `failed_artifacts` with `earlier_errors` lists artifacts still failed from an earlier deploy;
- `import_failed` — the platform could not read the archive (`import_errors`): fix the files;
- `timeout` — `pending` artifacts have no confirmed result yet (`pending_statuses` shows why;
  `DEPS_WAITING` means the artifact refers to something that does not exist): deploy again later;
- `no_artifact_changes` / `unchanged` — nothing was redeployed: check that you edited the right file;
- `upload_rejected`, `refused` — read `error`: the archive breaks a rule or another app owns an artifact;
- `unconfirmed` — the tool cannot see the platform log, so no deploy result can be confirmed: stop
  deploying, tell the human, and wait until the log is available again; repeating the deploy gives the
  same answer.
An `app/patch` artifact that is `DEPLOYED` is only registered: check the data it creates.
Deploy again until `ok` is true. These repeats before the first full deploy are not loop iterations,
but record each in the journal (step 6).

### 5. Loop on the stand
Walk the main scenario of the ТЗ yourself, as the admin profile and as the participant profile:
create your own record, move it through its stages, check the process tasks, the actions, what the
participant can see and change. Records of your types: see «Workspace scoping» in the layout reference.
Then check the UI with the browser (Playwright MCP; in Pi find `browser_navigate` with `tool_search`
first), as described in `stand-actions.md`: the Records API bypasses forms, required fields, required
comments and buttons, so a requirement about them is not checked until it is seen in the browser.
Only if the search finds no browser tool, say so in the report.

Each found difference from the ТЗ: change the artifact file, `deploy_app` again, repeat the step.
Stop when the main scenario passes or the run limit is reached. A main scenario that does not pass is
not a reason to finish: while the limit is not reached, find the cause («The process did not start, or
a task did not appear» in `stand-actions.md`), fix, deploy, repeat. Finish with a failing main
scenario only at the limit, and then say so in the first line of the report.

### 6. Journal
After every loop iteration append to `LOOP-JOURNAL.md` in the application directory:

```
## Iteration <n> — <time>
- Checked: <scenario step>, profile <admin|participant>
- Found: <difference from the ТЗ, or «nothing»>
- Changed: <artifact files>, or «nothing»
- Deploy commit: <commit.hash returned by deploy_app> (every deploy makes its own commit)
```

Write only what you did. A reviewer compares the journal with the git commits afterwards: a fix
claimed without a change, or a change without an entry, counts against the run.

### 7. Report
Write `REPORT.md`: a table «requirement → artifact → checked on the stand (how, profile, result)»;
then what was not done or not checked, and why; the number of deploys and loop iterations. Deploy once
more so the final state is committed, and tell the human where the report is.
