# Application layout for deploy_app

How to lay out an `ecos-apps` application directory so `deploy_app` can upload it into the
generation workspace. Facts checked on a local stand on 2026-11-10 unless marked otherwise.

## Directory

```
<app-dir>/                      # a git repository; deploy_app commits it after every deploy
  meta.json                     # {"id": "<app-id>", "name": {"ru": "...", "en": "..."}, "version": "1.0"}
  artifacts/
    model/type/<id>.yml
    model/permissions/<id>.json|yml
    model/num-template/<id>.yml
    model/aspect/<id>.yml
    ui/form/<id>.json
    ui/journal/<id>.yml|json
    ui/action/<id>.yml
    ui/dashboard/<id>.json
    ui/board/<id>.yml
    ui/menu/<id>.json
    process/bpmn/<id>.bpmn.xml
    process/dmn/<id>.dmn.xml
    notification/template/<id>/<id>.html.meta.yml   # plus <id>.html_ru.ftl, <id>.html_en.ftl
    app/patch/<id>.yml
    app/artifact-patch/<id>.yml
  process-src/<id>.bpmn.xml                         # semantic BPMN sources you edit; bpmn_layout writes artifacts/process/bpmn/
  PLAN.md  LOOP-JOURNAL.md  REPORT.md                # your files; not uploaded (only meta.json and artifacts/ are)
```

- The artifact id is the `id` inside the file (for BPMN: `ecos:processDefId` and the process id), not the
  file name; keep them equal anyway.
- `meta.json` `id`: lowercase letters, digits, dashes; **no workspace prefix** — the workspace is given to
  `deploy_app`. An id of an application already installed on the stand is refused.
- Hidden files and directories are not uploaded.

## Workspace scoping

- `deploy_app` uploads the archive into the generation workspace; every artifact in it is bound to that
  workspace (`eapps/artifact@<kind>$<ws>:<id>` on the stand).
- **Inside the archive refer to your own types as `emodel/type@CURRENT_WS:<id>`** (journals, forms,
  actions, permissions `typeRef`, BPMN `ecos:ecosType`). The platform rewrites `CURRENT_WS` to the
  workspace on upload. Platform base types stay global: `emodel/type@data-list`, `emodel/type@case`.
- A permissions matrix whose `typeRef` is not `CURRENT_WS:` is refused by `deploy_app`: a matrix replaces
  the matrix of the type it names, wherever that type lives.
- Do not add `artifacts/model/workspace/` — `deploy_app` creates the workspace.
- On the stand, records of your types are read and written with the type's records source: read
  `sourceId?str` of `emodel/type@<sys>:<id>` with `records_query` (`<sys>` is `workspace_system_id`
  returned by `deploy_app`, usually equal to the workspace id) — for an `ECOS_MODEL` type it is
  `emodel/<sys>:<id>` — and create records as `{"id": "emodel/<sys>:<id>@", "attributes":
  {"_workspace": "<ws>", ...}}`. `emodel/<id>@` without the workspace is "Source is not found".

## Deploy cycle

1. `deploy_app(app_dir, members=[<participant user>])` — uploads, waits until this upload is processed
   and returns every changed artifact with `DEPLOYED` / `DEPLOY_FAILED` and the platform error text.
   A result counts only when the platform log and the workspace's Records state agree.
2. A failed artifact: fix that file, deploy again. The platform also retries failed artifacts by itself,
   so an artifact that failed only because a dependency was not yet there may turn `DEPLOYED` later —
   `deploy_app` waits for one retry before reporting.
3. `failed_artifacts` lists every artifact of the app still failed on the stand, including ones this
   upload did not change; `earlier_errors` gives their last logged error text.
4. `unchanged` — the archive is byte-identical to the previous one; nothing was redeployed.
5. Every deploy makes one git commit of the application directory, also without file changes.
6. A patch: `app/artifact-patch` applies in the workspace written in its `workspace` field (empty means
   global), so write `workspace: <generation workspace>`. `app/patch` `DEPLOYED` means registered, not
   applied.

## Reference schemas

`references/schemas/` is a copy of the schemas the in-house assistant uses (source commit in
`schemas/SOURCE.md`). Two of them describe the assistant's intermediate format, not the artifact
file: `dmn/dmn-ir-schema*` and `dashboard/dashboard-ir-schema.json`. For DMN write DMN 1.3 XML; for
dashboards follow an existing dashboard on the stand (`records_query` on `uiserv/dashboard`).
