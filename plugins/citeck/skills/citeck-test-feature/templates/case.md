# Cases: <SECTION> (<ID-RANGE>)

Design/issue/code evidence: <links and source paths>.

> Every ID must also have exactly one row in `case-manifest.tsv`. Read `references/coverage-model.md`.
> All operations target `<BASE_URL>`; mutations use `<TEST_WORKSPACE>` and `<RUN_ID>`.

## <ID1>. <Case name>
**Kind:** <contract|journey|guard>  •  **Scopes:** <smoke,impact,full subset>  •
**Tier:** <A|B|A+B>  •  **Cluster:** <N>  •  **Tools:** `[HTTP]` `[RA]` `[PW]`  •
**Subagent:** `<runner>`
- **Trace:** <surface IDs, controller/tool/UI path, plan/bug IDs>.
- **Setup:** <isolated fixtures, personas, baseline snapshot and dependency state>.
- **Entry point:** <supported UI/API/external-system entry point>.
- **Steps:** <specific actions; for HITL always read the exact current `actions[].id`>.
- **Contract assertions:** <exact statuses/schema/intermediate state; no OR-pass>.
- **Terminal oracle:** <durable business postcondition, requery/reopen/external sink/process state>.
- **Forbidden side effects:** <records/actions/data that must remain absent or byte-identical>.
- **Evidence:** <HTTP/Records/UI/log/screenshot/sink artifacts required for PASS>.
- **Cleanup:** <delete only RUN_ID-owned data or `read-only`; verify baseline restored>.
- **Alternative coverage:** <rows in `scenario-matrix.tsv` covered by this ID>.

## <ID2>. <Case name>
**Kind:** contract  •  **Scopes:** full  •  **Tier:** A  •  **Cluster:** <N>  •
**Tools:** `[HTTP]` `[RA]`  •  **Subagent:** `<runner>`
- **Trace:** <...>.
- **Setup:** <...>.
- **Entry point:** <...>.
- **Steps:** <...>.
- **Contract assertions:** <...>.
- **Terminal oracle:** <exact response plus verified durable side effect or its absence>.
- **Forbidden side effects:** <...>.
- **Evidence:** <...>.
- **Cleanup:** <...>.
- **Alternative coverage:** <...>.
