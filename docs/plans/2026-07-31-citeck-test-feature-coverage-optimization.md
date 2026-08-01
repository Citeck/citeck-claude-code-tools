# Citeck test-feature: coverage and execution optimization

## Context

The `citeck-test-feature` skill produced a useful regression structure for `citeck-ai`, but a later
code-, plan- and defect-driven audit had to expand it to 313 cases across 15 suites. The audit found
no single missing testing technique; the recurring issue was that the skill optimized execution
before proving that the functional surface and terminal business journeys were complete.

The source checkout was first synchronized from v3.9.0 to v3.10.0. Version 3.10.0 added
`references/test-case-design.md`, but it still lacks a machine-checkable coverage contract.

## Observed gaps

1. Scoping started from the branch diff and issue instead of an inventory of public endpoints,
   assistant tools, state machines, background handlers, UI entry points and external effects.
2. API preview, plan creation, tool invocation and log messages could be accepted as E2E success
   without a persisted record, reopened UI state, completed process or observed external sink.
3. Tier B was defined as a small happy-path smoke set, so cross-tier cases could have no UI runner.
4. Alternative lifecycle branches were inconsistent: reject, cancel, retry, duplicate, stale,
   foreign-user, concurrency, restart and retention were not derived systematically.
5. Static examples contained volatile wire contracts such as hardcoded action identifiers.
6. Reports allowed SKIP while still permitting a positive release verdict.
7. There was no validator for case IDs, runner assignment, traceability, report completeness or
   stale prompt contracts.
8. Config restoration used destructive Git commands that could discard pre-existing user changes.

## Target model

Every case has an explicit kind:

| Kind | Purpose | Valid terminal evidence |
|---|---|---|
| `contract` | API/schema/boundary/negative matrix | Exact contract plus verified absence/presence of side effects |
| `journey` | User or external-system E2E | Supported entry point through durable business postcondition |
| `guard` | Unit/integration/defect invariant | Deterministic internal invariant |

API and UI are evidence channels, not mutually exclusive definitions of completeness. A capability
may have many fast contract cases and one representative terminal journey. Contract or guard cases
cannot replace that journey in traceability.

## Required planning artifacts

- `surface-inventory.tsv`: discovered controllers, tools, consumers, schedulers, UI actions,
  feature flags, record types and integrations.
- `TRACEABILITY.md`: capability and source evidence mapped to contract, journey and guard case IDs.
- `case-manifest.tsv`: one row per case with kind, tier, runner, dependencies and resource lock.
- `OPEN-DECISIONS.md`: unresolved product contracts, owner and blocking status.
- `validate-plan.py`: fail-closed structural validation.

## Discovery sources

The planning phase must inspect production code, frontend code, existing tests, tracker issue and
comments, design/development plans, defect history, configuration properties and previous reports.
The output is reviewed before case generation. An inventory item may be excluded only with a written
reason.

## Stateful coverage dimensions

For every stateful or mutating capability consider happy, reject, cancel, invalid/boundary,
duplicate/idempotent, stale/forged action, foreign principal/ACL, concurrency, dependency failure,
retry, timeout/retention, clear-context, restart and cleanup branches.

## Execution optimization

- Use `SCOPE=smoke|impact|full`; only `full` may produce a full release verdict.
- Build an execution DAG from dependencies and resource locks.
- Parallelize read-only contract cases; serialize cases sharing a record, conversation or mutable
  configuration.
- Reuse setup and representative journeys, but never evidence from another deployed commit for a
  full run.
- Run one UI journey per distinct interaction contract; cover data matrices and boundaries through
  fast contract cases.
- Reconcile API and UI evidence into the original `A+B` case ID.

## Fail-closed release rules

For a full run every required case must be PASS. `FAIL`, `BLOCKED`, `NOT_RUN`, `SKIP` or `PARTIAL`
means `NOT_READY`. The report must capture HEAD, deployed SHA, environment, dependencies, evidence,
cleanup and forbidden-side-effect checks.

## Independent review follow-up

Independent agents demonstrated fail-open paths in the first implementation: `full` without a
report, PASS without evidence, an empty inventory, a non-required terminal journey, free-form
alternative coverage and trace rows unrelated to inventory capabilities. The hardened design also
requires:

- non-design scopes always pass `--report`, and source HEAD equals deployed SHA;
- at least one included surface and a required terminal journey per included capability;
- `scenario-matrix.tsv` with all state dimensions and concrete case IDs or an explicit rationale;
- exact inventory/manifest/traceability capability and case-kind reconciliation;
- manifest scope membership and an acyclic case dependency DAG;
- terminal, forbidden-effect and cleanup evidence for PASS, with separate `A:` and `B:` proof;
- discovery of `ConfigurationProperties(prefix=...)` and distinct scheduled methods.

## Implementation

1. Add `references/coverage-model.md`.
2. Update skill flow, tier model, case design and orchestration.
3. Expand case, plan, report and runner templates.
4. Add case manifest, surface inventory, scenario matrix, traceability and open-decisions templates.
5. Add deterministic scaffold, async HTTP and plan validation scripts.
6. Add pytest coverage for scaffolding, validation and static safety rules.
7. Remove stale action IDs and destructive restore instructions from the AI profile.

## Acceptance

- A generated plan contains every required planning artifact and no file is silently overwritten.
- Validator rejects orphan cases/surfaces, missing runners, incomplete case blocks, invalid A+B
  assignments, unknown trace IDs and full reports with non-PASS required cases.
- The skill contains no generic hardcoded HITL actions and no destructive Git restore command.
- Plugin unit tests and script syntax checks pass.
