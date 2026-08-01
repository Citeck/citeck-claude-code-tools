# Coverage Model

Use this reference during discovery, case design, review and final release gating.

## Case kinds

| Kind | Purpose | Terminal rule |
|---|---|---|
| `contract` | Endpoint/tool/schema, validation, boundary or negative behavior | Verify exact response and durable side effect or its absence |
| `journey` | Supported user/external-system E2E | Continue to the observable business outcome and reopen/requery it |
| `guard` | Unit/integration/known-defect invariant | Verify the deterministic invariant; never claim E2E coverage |

Evidence channels are orthogonal to kind:

- `A`: HTTP, Records API, logs, binary inspection or unit tests.
- `B`: real UI through Playwright.
- `A+B`: one case ID that receives PASS only after API/Records and UI evidence are reconciled.

Do not call a preview, generated plan, action card, tool invocation, intermediate state or log line
an E2E result. They can be assertions inside a journey, not its terminal oracle.

## Mandatory discovery inventory

Inspect and record:

1. REST/RPC controllers and every public method/path.
2. Assistant/platform tools and their read/write classification.
3. Event consumers, external tasks, schedulers, callbacks and background workers.
4. State stores, action identifiers, state transitions, timeout and retention behavior.
5. Configuration properties, feature flags, limits and provider variants.
6. Record types, content stores, external sinks and audit/activity records.
7. UI entry points, actions, rendering components, reload/reconnect behavior and accessibility.
8. Existing unit/integration/E2E tests.
9. Tracker requirements, development plans, defect history and previous run reports.

Write the result to `surface-inventory.tsv`. Every included surface maps to at least one case. Every
excluded surface has a reason and owner.

## Capability traceability

Each capability in `TRACEABILITY.md` must map:

`source evidence -> contract cases -> terminal journey -> guard cases -> external oracle`

A contract or guard may support diagnosis but cannot replace the terminal journey. When the product
has no UI, use the supported external-system/API entry point and document why it is terminal.

## Stateful scenario matrix

For every included capability, record every dimension in `scenario-matrix.tsv`. An applicable
dimension is required and maps to concrete case IDs; a non-applicable dimension has an explicit
rationale. Free-form `N/A` in a case does not satisfy this gate.

| Dimension | Required question |
|---|---|
| Happy | Does the complete business outcome exist and remain after reload/requery? |
| Reject/cancel | Is state cleared and are forbidden mutations absent? |
| Invalid/boundary | Are empty, malformed, minimum, maximum and oversized inputs deterministic? |
| Duplicate | Is retry/double-submit idempotent? |
| Stale/forged | Are old, unknown and cross-conversation actions denied? |
| Principal/ACL | Are role, record ACL and owner isolation enforced? |
| Concurrency | Is the winner deterministic and is partial state cleaned? |
| Dependency failure | Is failure honest, localized and recoverable? |
| Retry | Are completed steps reused without duplicate effects? |
| Timeout/retention | Are active and terminal states expired according to contract? |
| Clear/restart | Is conversation/session state correctly retained or removed? |
| Cleanup | Are all run-owned artifacts removed without touching pre-existing data? |

Use decision tables or pairwise selection for large role/provider/field matrices. Do not hide
untested combinations behind an OR-pass.

## Scope modes

- `smoke`: fast liveness and one golden journey; never a release verdict.
- `impact`: changed capabilities, dependency closure, permanent defect guards and core smoke.
- `full`: every `required=yes` manifest row on the same HEAD/deployed SHA.

Store scope membership in the manifest `scopes` column. `dependencies` contains case IDs (or
`none`), not service names; dependency services and health evidence belong in the run report.

Previous evidence may inform `impact` selection. It does not satisfy a `full` run unless it is from
the same deployed SHA, environment contract and unchanged dependency surface.

## Full gate

`PASS` is the only successful status for a required full-run case. `FAIL`, `BLOCKED`, `NOT_RUN`,
`SKIP` and `PARTIAL` all produce `NOT_READY`.

Each PASS row must reference:

- terminal evidence;
- external/Records/UI oracle as applicable;
- forbidden-side-effect evidence;
- cleanup evidence or an explicit read-only marker.

Execution scopes (`smoke`, `impact`, `full`) require `--report`. The validator rejects an empty
inventory, missing scenario dimensions, mismatched source/deployed SHA and PASS rows without
evidence. For `A+B`, terminal evidence contains separate `A:` and `B:` channels.

The Final Gate is scope-aware, so a limited run never has to attest a full-run claim:

| Gate criteria | `smoke` / `impact` | `full` |
|---|---|---|
| validator, HEAD=DEPLOYED_SHA, surfaces traced, A+B reconciled, external effects, cleanup | must be checked | must be checked |
| Unit and required integration suites, every required full-run case is PASS | must stay **unchecked** | must be checked |

A smoke/impact report additionally states `**Scope limitation:**` — what the run does not claim.
Checking a full-only criterion under a limited scope is itself a validation error. Unchecked boxes
are only inspected inside the `## Final Gate` section, so defect and follow-up checklists elsewhere
in the report are free-form.
