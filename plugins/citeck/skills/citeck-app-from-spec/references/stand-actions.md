# Working on the stand

How to walk the scenario on the stand: records, process tasks, the UI. Every fact here was checked on
a local stand on 2026-11-10 (run `pi-run1`); `<sys>` is `workspace_system_id` from `deploy_app`,
`<ws>` the workspace id.

## Records of your types (Records API)

- Create: `records_mutate` with `{"id": "emodel/<sys>:<type-id>@", "attributes": {"_workspace?str": "<ws>", ...}}`
  under the profile of the user who creates it (the participant for «the employee submits»).
- Attribute suffixes in a mutation: `?str`, `?num`, `?bool`, `?id` (refs). **A date goes as `?str`
  `"YYYY-MM-DD"`**: `?date` is ignored silently, the field stays empty and a mandatory field fails with
  «Mandatory attributes are empty».
- A failed create may still take a number from the number template: avoid trial-and-error creates;
  read `platform_errors` of the failed call first.
- Read back: `records_query` with `record_ids` and attributes like `_status?str`, `_docNum?num`,
  `<field>?str`, `<person>?id`.

## Process tasks (`eproc/proc-task`)

- Open tasks of a record: `records_query` on source `eproc/proc-task`, language `predicate`,
  query `{"t": "eq", "a": "document", "v": "<record ref>"}` (`document`, not `documentRef`).
  Useful attributes: `name?disp`, `possibleOutcomes[]?json` (ids and `config.commentRequired`),
  `actors[]?id` (who may complete it), `formRef?id`, `ended?str`. A completed task leaves this query.
- Complete a task with an outcome: `records_mutate` on `eproc/proc-task@<task id>` with
  `{"_workspace?str": "<ws>", "outcome_<outcome id>?bool": true, "comment?str": "...", <fields of the task form>}`
  under the profile of an actor of the task. Task form fields (e.g. a person chosen on approval) go in
  the same mutation; they reach the process as variables — writing them into the record is the
  process's job (a script task), not automatic.
- A script task that throws makes the whole completion fail (HTTP 500 with the script's message, the task
  stays open, the status does not change) — a valid way to enforce a rule.
- Records API completion bypasses the task form: required fields, `commentRequired`, buttons. Check
  those in the browser.

## The process did not start, or a task did not appear

A process that throws in a script or service task right after its start leaves no task, and its error
is **not** in the `ecos-apps` log that `deploy_app` reads: the start is retried in the background and
fails again (seen 2026-11-10, run `pi-crm1`).

- When: a record is created and ~30 s later it has no open task where the process should have made
  one, or the status and fields the process sets are unchanged.
- Read the error: `records_query` on source `eproc/bpmn-delayed-start-cmd`, language `predicate`,
  query `{"t": "eq", "a": "businessKey", "v": "<record ref>"}`, attributes `lastError?str`,
  `_created?str`. `lastError` is the exception text of the failed step: fix that step in the process
  file, `bpmn_validate`, `bpmn_layout`, `deploy_app`, then create a **new** record and check again.
- Nothing found there and still no task: check that the process is enabled, starts automatically and
  is bound to your type.

## Browser (Playwright MCP)

In Pi the browser tools are deferred like the Citeck ones: find them with `tool_search`
(`browser_navigate browser_snapshot`) before deciding there is no browser. Never write «no browser» in
the report without that search.

- Log in (basic auth stands): open `http://<user>:<password>@<host>/` once, then open every page
  without credentials — with credentials in the URL the application's own requests fail.
- Several users side by side: one tab per user in its own context —
  `browser_tabs` with `action: "new"`, `isolatedContext: "<user>"`, `url: "http://<user>:<password>@<host>/v2/"`,
  then switch with `browser_tabs` `action: "select"`, `index: <n>` (seen working 2026-11-10, run `pi-run2`).
- Pages: journal `/v2/journals?ws=<ws>&journalId=<sys>:<journal-id>`; record card
  `/v2/dashboard?recordRef=<record ref>&ws=<ws>`; the user's open tasks `/v2/journals?ws=<ws>&journalId=bpmn-active-tasks`.
- One `browser_snapshot` per screen state; `browser_find` for a single check.
- An empty snapshot (empty accessibility tree) does not mean an empty page: wait (`browser_wait_for`),
  take a `browser_take_screenshot` and snapshot again before writing «the page is empty»
  (run `pi-crm1`: a rendered page was reported as empty this way).
- After each screen: `browser_console_messages` (level error) and `browser_network_requests`; report the
  errors of your pages. The local stand may show unrelated errors (an unavailable `integrations` app,
  the AI assistant endpoint) — name them as such.
- ECOS forms in Playwright (seen 2026-11-10):
  - the record card and an open edit dialog render the same field ids (`#quantity` twice): aim at the
    dialog's copy (the last match, or a selector inside the dialog), or add `:visible`;
  - a date field opens a calendar; typing the date did not set the value — pick the day by its label:
    `.flatpickr-day[aria-label="November 25, 2026"] >> nth=0`;
  - a click on a button that waits until timeout usually hit a hidden duplicate: use `button:text-is("…"):visible`;
  - a disabled submit button means the form does not validate: look for the required field it flags.
- What to check in the UI, as the participant and as the admin: the record form opens and its required
  fields block saving; each task form opens from the task, shows its fields and outcome buttons, a
  required comment is enforced on the outcome that needs it; the journal opens from the workspace menu,
  shows the columns and filters by state; texts are in the user's language, no raw ids or `null`.

## Menu

The workspace gets its own left menu from the platform; journals of the workspace's types appear in it
under «Sections» without a `ui/menu` artifact (seen 2026-11-10: a `ui/menu` artifact of the app was
deployed but not the menu shown). Check the menu in the browser before adding a `ui/menu` artifact.
