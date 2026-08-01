# Test Run Report: <ISSUE> — <FEATURE>

**Date:** <DATE>  •  **Run-id:** `<RUN_ID>`  •  **Scope:** `<smoke|impact|full>`
**Tester:** <AUTHOR>
**Environment:** `<BASE_URL>` (profile `<PROFILE>`, `<CLASSIFICATION>`)
**Source:** `<BRANCH>` @ `<HEAD_SHA>`  •  **Deployed:** `<DEPLOYED_SHA>`
**Provider/model/config:** <values>  •  **Dirty baseline:** <captured paths or clean>
**Scope limitation:** <required for smoke/impact: what this run does NOT claim; delete for full>

## Dependencies

| Dependency | Required | Version/config | Health evidence | Failure route | Status |
|---|---|---|---|---|---|
| <service/sink/provider> | yes | | | | |

## Summary

| Suite | Total | PASS | FAIL | BLOCKED | NOT_RUN | SKIP | PARTIAL |
|---|---:|---:|---:|---:|---:|---:|---:|
| <suite> | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **Total** | **0** | **0** | **0** | **0** | **0** | **0** | **0** |

## Results

One row per `case-manifest.tsv` ID. Never merge IDs or omit an unexecuted row.

| ID | Kind | Tier | Status | Terminal evidence | Forbidden effects | Cleanup |
|---|---|---|---|---|---|---|
| <ID> | <contract|journey|guard> | <A|B|A+B> | <PASS|FAIL|BLOCKED|NOT_RUN|SKIP|PARTIAL> | <A: API/Records evidence; B: UI evidence for A+B> | <absence evidence> | <verification or read-only> |

For A+B, terminal evidence uses explicit `A:` and `B:` channels. The row stays
`BLOCKED(PENDING_A|PENDING_UI)` until both channels are reconciled.

## Open Decisions

| Decision | Owner | Blocking | Resolution used by run |
|---|---|---|---|
| <DEC-ID> | | | |

## Defects

| # | Description | Repro/evidence | Severity | Issue / Commit |
|---|---|---|---|---|
| | | | | |

## Cleanup

| Resource/fixture | Baseline | Action | Verification |
|---|---|---|---|
| <RUN_ID-owned resource> | absent | deleted | Records/API check |

## Final Gate

Every scope must check these:

- [ ] `validate-plan.py` passes and report has exactly one row per manifest ID
- [ ] HEAD equals DEPLOYED_SHA and dependency contract is recorded
- [ ] All included surfaces are traced to cases and a terminal journey
- [ ] A+B cases contain reconciled API/RA and UI evidence
- [ ] External effects and forbidden side effects were independently verified
- [ ] Cleanup restored captured baseline without deleting pre-existing changes

Only `scope=full` may check these; on smoke/impact they stay unchecked:

- [ ] Unit and required integration suites are green
- [ ] Every required full-run case is PASS

For `scope=full`, any required `FAIL/BLOCKED/NOT_RUN/SKIP/PARTIAL` means:

**Decision:** `NOT_READY`

For `smoke`/`impact`, record the scope-limited result in **Scope limitation:** above and never
present it as a full regression or a release verdict.
