#!/usr/bin/env python3
"""Validate coverage, runner assignment and run completeness of a Citeck test plan."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


CASE_BLOCK = re.compile(
    r"^#{2,3}\s+([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)?(?:\.\d+)?)\..*?"
    r"(?=^#{2,3}\s+[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)?(?:\.\d+)?\.|\Z)",
    re.M | re.S,
)
REQUIRED_LABELS = (
    "**Kind:**",
    "**Tier:**",
    "**Trace:**",
    "**Setup:**",
    "**Entry point:**",
    "**Steps:**",
    "**Terminal oracle:**",
    "**Forbidden side effects:**",
    "**Evidence:**",
    "**Cleanup:**",
    "**Alternative coverage:**",
)
MANIFEST_HEADER = (
    "case_id",
    "case_file",
    "kind",
    "tier",
    "cluster",
    "required",
    "scopes",
    "runner_prompt",
    "dependencies",
    "resource_lock",
    "capability",
)
SURFACE_HEADER = (
    "surface_id",
    "kind",
    "source",
    "operation",
    "capability",
    "included",
    "case_ids",
    "exclusion_reason",
    "owner",
)
SCENARIO_HEADER = (
    "capability",
    "dimension",
    "applicable",
    "required",
    "case_ids",
    "rationale",
)
SCENARIO_DIMENSIONS = {
    "happy",
    "reject-cancel",
    "invalid-boundary",
    "duplicate",
    "stale-forged",
    "principal-acl",
    "concurrency",
    "dependency-failure",
    "retry",
    "timeout-retention",
    "clear-restart",
    "cleanup",
}
VALID_STATUSES = {"PASS", "FAIL", "BLOCKED", "NOT_RUN", "SKIP", "PARTIAL"}
# Gate criteria every executed scope must attest.
COMMON_GATE_MARKERS = (
    "validate-plan.py",
    "HEAD equals DEPLOYED_SHA",
    "included surfaces",
    "A+B cases",
    "External effects",
    "Cleanup restored",
)
# Gate criteria only a full run may claim; smoke/impact must leave them unchecked.
FULL_GATE_MARKERS = (
    "Unit and required integration",
    "required full-run case",
)


class Validation:
    def __init__(self, plan_dir: Path):
        self.plan_dir = plan_dir
        self.errors: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def relative_file(self, value: str) -> Path | None:
        path = (self.plan_dir / value).resolve()
        try:
            path.relative_to(self.plan_dir)
        except ValueError:
            self.error(f"path escapes plan directory: {value}")
            return None
        if not path.is_file():
            self.error(f"missing file: {value}")
            return None
        return path


def meaningful(value: str) -> bool:
    value = value.strip()
    return bool(value and value != "-" and "<" not in value and ">" not in value)


def split_values(value: str) -> set[str]:
    return {
        item.strip().strip("`")
        for item in value.split(",")
        if item.strip() and item.strip().lower() not in {"-", "`-`", "none", "`none`"}
    }


def read_tsv(validation: Validation, filename: str, expected_header: tuple[str, ...]) -> list[dict]:
    path = validation.relative_file(filename)
    if path is None:
        return []
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if tuple(reader.fieldnames or ()) != expected_header:
            validation.error(
                f"{filename}: expected header {expected_header}, got {tuple(reader.fieldnames or ())}"
            )
            return []
        return list(reader)


def collect_cases(validation: Validation) -> tuple[dict[str, Path], dict[str, str]]:
    case_paths: dict[str, Path] = {}
    blocks: dict[str, str] = {}
    cases_dir = validation.plan_dir / "cases"
    if not cases_dir.is_dir():
        validation.error("missing cases/ directory")
        return case_paths, blocks
    for path in sorted(cases_dir.glob("*.md")):
        for match in CASE_BLOCK.finditer(path.read_text()):
            case_id = match.group(1)
            if case_id in case_paths:
                validation.error(
                    f"duplicate case ID {case_id}: {case_paths[case_id].name}, {path.name}"
                )
            case_paths[case_id] = path
            blocks[case_id] = match.group(0)
    if not case_paths:
        validation.error("no case IDs found in cases/*.md")
    return case_paths, blocks


def validate_case_blocks(validation: Validation, blocks: dict[str, str]) -> None:
    for case_id, block in blocks.items():
        for label in REQUIRED_LABELS:
            match = re.search(rf"{re.escape(label)}\s*(.*)", block)
            if not match:
                validation.error(f"{case_id}: missing required label {label}")
            elif not meaningful(match.group(1)):
                validation.error(f"{case_id}: {label} must have a concrete value")
        if not re.search(r"\*\*Kind:\*\*\s*(contract|journey|guard)(?:\s|•)", block):
            validation.error(f"{case_id}: invalid or missing Kind")
        if not re.search(r"\*\*Tier:\*\*\s*(A\+B|A|B)(?:\s|•)", block):
            validation.error(f"{case_id}: invalid or missing Tier")


def validate_dependencies(validation: Validation, rows: list[dict], known_ids: set[str]) -> None:
    graph: dict[str, set[str]] = {}
    for row in rows:
        case_id = row["case_id"]
        dependencies = split_values(row["dependencies"])
        unknown = dependencies - known_ids
        if unknown:
            validation.error(f"{case_id}: unknown dependencies {sorted(unknown)}")
        if case_id in dependencies:
            validation.error(f"{case_id}: cannot depend on itself")
        graph[case_id] = dependencies & known_ids

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(case_id: str) -> None:
        if case_id in visiting:
            validation.error(f"case dependency cycle includes {case_id}")
            return
        if case_id in visited:
            return
        visiting.add(case_id)
        for dependency in graph.get(case_id, set()):
            visit(dependency)
        visiting.remove(case_id)
        visited.add(case_id)

    for case_id in graph:
        visit(case_id)


def validate_manifest(
    validation: Validation, case_paths: dict[str, Path], blocks: dict[str, str]
) -> tuple[list[dict], dict[str, dict]]:
    rows = read_tsv(validation, "case-manifest.tsv", MANIFEST_HEADER)
    ids = [row["case_id"] for row in rows]
    for duplicate, count in Counter(ids).items():
        if count > 1:
            validation.error(f"case-manifest.tsv: duplicate case ID {duplicate}")
    manifest = {row["case_id"]: row for row in rows}
    known_ids = set(manifest)
    for case_id in sorted(set(case_paths) - known_ids):
        validation.error(f"case {case_id} has no manifest row")
    for case_id in sorted(known_ids - set(case_paths)):
        validation.error(f"manifest references unknown case {case_id}")

    for row in rows:
        case_id = row["case_id"]
        if row["kind"] not in {"contract", "journey", "guard"}:
            validation.error(f"{case_id}: invalid manifest kind {row['kind']!r}")
        if row["tier"] not in {"A", "B", "A+B"}:
            validation.error(f"{case_id}: invalid manifest tier {row['tier']!r}")
        if row["required"] not in {"yes", "no"}:
            validation.error(f"{case_id}: required must be yes/no")
        scopes = split_values(row["scopes"])
        if not scopes or not scopes <= {"smoke", "impact", "full"}:
            validation.error(f"{case_id}: scopes must use smoke,impact,full")
        if row["required"] == "yes" and "full" not in scopes:
            validation.error(f"{case_id}: required case must include full scope")
        if not meaningful(row["capability"]):
            validation.error(f"{case_id}: capability must be concrete")
        if not row["resource_lock"]:
            validation.error(f"{case_id}: resource_lock must be explicit (`none` is allowed)")
        case_file = validation.relative_file(row["case_file"])
        if case_id in case_paths and case_file and case_file != case_paths[case_id].resolve():
            validation.error(f"{case_id}: manifest case_file does not own the case")

        prompts = [item.strip() for item in row["runner_prompt"].split(",") if item.strip()]
        if not prompts or "-" in prompts or len(prompts) != len(set(prompts)):
            validation.error(f"{case_id}: runner_prompt must contain unique concrete prompt paths")
        for prompt in prompts:
            if prompt == "-":
                continue
            prompt_path = validation.relative_file(prompt)
            # A trailing period ends a sentence; only `.<digit>` means a different sub-case ID.
            if prompt_path and not re.search(
                rf"(?<![A-Z0-9.-]){re.escape(case_id)}(?![A-Z0-9-])(?!\.\d)",
                prompt_path.read_text(),
            ):
                validation.error(f"{case_id}: runner prompt {prompt} does not mention exact case ID")
        if row["tier"] == "A+B":
            has_a = any("tier-a" in Path(prompt).name.lower() for prompt in prompts)
            has_b = any("tier-b" in Path(prompt).name.lower() for prompt in prompts)
            if len(prompts) < 2 or not has_a or not has_b:
                validation.error(f"{case_id}: A+B requires distinct tier-a and tier-b runner prompts")
        elif row["tier"] == "A" and not all(
            "tier-a" in Path(prompt).name.lower() for prompt in prompts
        ):
            validation.error(f"{case_id}: Tier A requires only tier-a runner prompts")
        elif row["tier"] == "B" and not all(
            "tier-b" in Path(prompt).name.lower() for prompt in prompts
        ):
            validation.error(f"{case_id}: Tier B requires only tier-b runner prompts")

        block = blocks.get(case_id, "")
        kind_match = re.search(r"\*\*Kind:\*\*\s*(contract|journey|guard)", block)
        tier_match = re.search(r"\*\*Tier:\*\*\s*(A\+B|A|B)", block)
        if kind_match and kind_match.group(1) != row["kind"]:
            validation.error(f"{case_id}: case Kind differs from manifest")
        if tier_match and tier_match.group(1) != row["tier"]:
            validation.error(f"{case_id}: case Tier differs from manifest")
    validate_dependencies(validation, rows, known_ids)
    return rows, manifest


def validate_surfaces(validation: Validation, manifest: dict[str, dict]) -> dict[str, dict]:
    rows = read_tsv(validation, "surface-inventory.tsv", SURFACE_HEADER)
    included: dict[str, dict] = {}
    for row in rows:
        surface_id = row["surface_id"]
        if row["included"] not in {"yes", "no"}:
            validation.error(f"{surface_id}: included must be yes/no")
            continue
        case_ids = split_values(row["case_ids"])
        unknown = case_ids - set(manifest)
        if unknown:
            validation.error(f"{surface_id}: unknown case IDs {sorted(unknown)}")
        if row["included"] == "yes":
            included[surface_id] = row
            if not meaningful(row["capability"]):
                validation.error(f"{surface_id}: included surface capability is missing")
            if not case_ids:
                validation.error(f"{surface_id}: included surface has no case IDs")
            elif not any(
                case_id in manifest
                and manifest[case_id]["required"] == "yes"
                and "full" in split_values(manifest[case_id]["scopes"])
                for case_id in case_ids
            ):
                validation.error(
                    f"{surface_id}: included surface needs a required full case in case_ids"
                )
            if not meaningful(row["owner"]) or row["owner"] == "UNASSIGNED":
                validation.error(f"{surface_id}: included surface owner is unassigned")
            for case_id in case_ids & set(manifest):
                if manifest[case_id]["capability"] != row["capability"]:
                    validation.error(f"{surface_id}: case {case_id} belongs to another capability")
        elif (
            not meaningful(row["exclusion_reason"])
            or not meaningful(row["owner"])
            or row["owner"] == "UNASSIGNED"
        ):
            validation.error(f"{surface_id}: excluded surface needs reason and owner")
    if not included:
        validation.error("surface-inventory.tsv: no included surfaces; coverage cannot be claimed")
    return included


def parse_trace_rows(validation: Validation) -> list[list[str]]:
    path = validation.relative_file("TRACEABILITY.md")
    if path is None:
        return []
    rows: list[list[str]] = []
    for line in path.read_text().splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) == 6 and cells[0] not in {"Capability", "---"}:
            rows.append(cells)
    return rows


def validate_traceability(
    validation: Validation, manifest: dict[str, dict], included: dict[str, dict]
) -> None:
    trace_rows = parse_trace_rows(validation)
    by_capability: dict[str, list[str]] = {}
    for cells in trace_rows:
        capability = cells[0]
        if capability in by_capability:
            validation.error(f"TRACEABILITY.md: duplicate capability {capability!r}")
        by_capability[capability] = cells
        columns = ((2, "contract"), (3, "journey"), (4, "guard"))
        for index, expected_kind in columns:
            for case_id in split_values(cells[index]):
                row = manifest.get(case_id)
                if row is None:
                    validation.error(f"TRACEABILITY.md: unknown case {case_id}")
                elif row["kind"] != expected_kind or row["capability"] != capability:
                    validation.error(
                        f"TRACEABILITY.md: {case_id} must be {expected_kind} for {capability!r}"
                    )
        journeys = split_values(cells[3])
        if not any(
            case_id in manifest
            and manifest[case_id]["kind"] == "journey"
            and manifest[case_id]["required"] == "yes"
            for case_id in journeys
        ):
            validation.error(
                f"TRACEABILITY.md capability {capability!r} has no required journey in Terminal journey"
            )
        if not meaningful(cells[5]):
            validation.error(f"TRACEABILITY.md capability {capability!r} has no external oracle")

    surfaces_by_capability: dict[str, set[str]] = defaultdict(set)
    cases_by_capability: dict[str, set[str]] = defaultdict(set)
    for surface_id, row in included.items():
        surfaces_by_capability[row["capability"]].add(surface_id)
        cases_by_capability[row["capability"]].update(split_values(row["case_ids"]))
    for capability, surface_ids in surfaces_by_capability.items():
        cells = by_capability.get(capability)
        if cells is None:
            validation.error(f"TRACEABILITY.md: missing capability {capability!r}")
            continue
        source_evidence = split_values(cells[1].replace(" ", ","))
        for surface_id in sorted(surface_ids - source_evidence):
            validation.error(f"TRACEABILITY.md: {capability!r} does not map surface {surface_id}")
        trace_cases = split_values(",".join(cells[2:5]))
        missing_cases = cases_by_capability[capability] - trace_cases
        if missing_cases:
            validation.error(
                f"TRACEABILITY.md: {capability!r} omits inventory cases {sorted(missing_cases)}"
            )
    for case_id, row in manifest.items():
        cells = by_capability.get(row["capability"])
        if cells is None:
            validation.error(
                f"TRACEABILITY.md: manifest capability {row['capability']!r} is missing for {case_id}"
            )
        elif case_id not in split_values(",".join(cells[2:5])):
            validation.error(f"TRACEABILITY.md does not map case {case_id} in its capability row")


def validate_scenarios(
    validation: Validation, manifest: dict[str, dict], included: dict[str, dict]
) -> None:
    rows = read_tsv(validation, "scenario-matrix.tsv", SCENARIO_HEADER)
    capabilities = {row["capability"] for row in included.values()}
    indexed: dict[tuple[str, str], dict] = {}
    for row in rows:
        key = (row["capability"], row["dimension"])
        if key in indexed:
            validation.error(f"scenario-matrix.tsv: duplicate row {key}")
        indexed[key] = row
        if row["capability"] not in capabilities:
            validation.error(f"scenario-matrix.tsv: unknown capability {row['capability']!r}")
        if row["dimension"] not in SCENARIO_DIMENSIONS:
            validation.error(f"scenario-matrix.tsv: invalid dimension {row['dimension']!r}")
        if row["applicable"] not in {"yes", "no"} or row["required"] not in {"yes", "no"}:
            validation.error(f"scenario-matrix.tsv: {key} applicable/required must be yes/no")
        case_ids = split_values(row["case_ids"])
        if row["applicable"] == "yes":
            if row["required"] != "yes" or not case_ids:
                validation.error(f"scenario-matrix.tsv: applicable {key} must be required with cases")
        elif row["required"] != "no" or not meaningful(row["rationale"]):
            validation.error(f"scenario-matrix.tsv: non-applicable {key} needs required=no and rationale")
        for case_id in case_ids:
            case = manifest.get(case_id)
            if case is None:
                validation.error(f"scenario-matrix.tsv: {key} references unknown case {case_id}")
            elif case["capability"] != row["capability"]:
                validation.error(f"scenario-matrix.tsv: {case_id} belongs to another capability")
            elif row["applicable"] == "yes" and (
                case["required"] != "yes" or "full" not in split_values(case["scopes"])
            ):
                validation.error(
                    f"scenario-matrix.tsv: applicable {key} uses non-required full case {case_id}"
                )
        if row["dimension"] == "happy" and row["applicable"] == "yes" and not any(
            case_id in manifest and manifest[case_id]["kind"] == "journey" for case_id in case_ids
        ):
            validation.error(f"scenario-matrix.tsv: {key} requires a journey case")
    for capability in capabilities:
        for dimension in SCENARIO_DIMENSIONS:
            if (capability, dimension) not in indexed:
                validation.error(f"scenario-matrix.tsv: missing {capability!r}/{dimension}")


def validate_decisions(validation: Validation) -> None:
    path = validation.relative_file("OPEN-DECISIONS.md")
    if path is None:
        return
    for line in path.read_text().splitlines():
        if line.startswith("| DEC-"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) >= 6 and cells[4].lower() == "yes" and cells[5].upper() == "OPEN":
                validation.error(f"{cells[0]}: blocking decision is OPEN")


def validate_runner_contracts(validation: Validation) -> None:
    prompts_dir = validation.plan_dir / "subagent-prompts"
    if not prompts_dir.is_dir():
        validation.error("missing subagent-prompts/ directory")
        return
    paths = list(prompts_dir.rglob("*.md")) + list((validation.plan_dir / "cases").glob("*.md"))
    forbidden = {
        r"(?:[\"']?action[\"']?)\s*:\s*[\"']?(?:confirm|reject|approve)[\"']?": "generic hardcoded action",
        r"action\s*=\s*[\"'](?:confirm|reject|approve)[\"']": "generic hardcoded action",
        r"git\s+(?:checkout|restore)\s+--": "destructive Git restore",
    }
    for path in paths:
        text = path.read_text()
        for pattern, description in forbidden.items():
            if re.search(pattern, text, re.I):
                validation.error(f"{path.relative_to(validation.plan_dir)}: {description}")


def validate_report(
    validation: Validation, rows: list[dict], report_name: str, scope: str
) -> None:
    path = validation.relative_file(report_name)
    if path is None:
        return
    text = path.read_text()
    for marker in (
        "**Environment:**",
        "**Provider/model/config:**",
        "**Dirty baseline:**",
        "## Dependencies",
        "## Results",
        "## Final Gate",
    ):
        if marker not in text:
            validation.error(f"{report_name}: missing required report section {marker}")
    for label in ("Environment", "Provider/model/config", "Dirty baseline"):
        match = re.search(rf"\*\*{re.escape(label)}:\*\*\s*([^\n•]+)", text)
        if not match or not meaningful(match.group(1)):
            validation.error(f"{report_name}: {label} must have a concrete value")
    scope_match = re.search(r"\*\*Scope:\*\*\s*`?([a-z]+)`?", text)
    if not scope_match or scope_match.group(1) != scope:
        validation.error(f"{report_name}: report Scope must equal CLI scope={scope}")
    if scope != "full":
        limitation = re.search(r"\*\*Scope limitation:\*\*\s*([^\n]+)", text)
        if not limitation or not meaningful(limitation.group(1)):
            validation.error(
                f"{report_name}: scope={scope} must state an explicit **Scope limitation:**"
            )
    sha_match = re.search(
        r"\*\*Source:\*\*.*?@\s*`?([0-9a-f]{7,40})`?.*?\*\*Deployed:\*\*\s*`?([0-9a-f]{7,40})`?",
        text,
        re.I,
    )
    if not sha_match or sha_match.group(1).lower() != sha_match.group(2).lower():
        validation.error(f"{report_name}: Source HEAD and DEPLOYED_SHA must be concrete and equal")

    manifest = {row["case_id"]: row for row in rows}
    results: dict[str, list[list[str]]] = defaultdict(list)
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) == 7 and cells[0] in manifest:
            results[cells[0]].append(cells)
    selected = {
        row["case_id"]
        for row in rows
        if (scope == "full" and row["required"] == "yes")
        or (scope in {"smoke", "impact"} and scope in split_values(row["scopes"]))
    }
    changed = True
    while changed:
        changed = False
        for case_id in tuple(selected):
            for dependency in split_values(manifest[case_id]["dependencies"]):
                if dependency in manifest and dependency not in selected:
                    selected.add(dependency)
                    changed = True
    if not selected:
        validation.error(f"{report_name}: scope={scope} selects no cases")
    for case_id, row in manifest.items():
        values = results.get(case_id, [])
        if len(values) != 1:
            validation.error(f"{report_name}: expected one row for {case_id}, got {len(values)}")
            continue
        cells = values[0]
        if cells[1] != row["kind"] or cells[2] != row["tier"]:
            validation.error(f"{report_name}: {case_id} Kind/Tier differs from manifest")
        status = cells[3].split("(", 1)[0]
        if status not in VALID_STATUSES:
            validation.error(f"{report_name}: {case_id} has invalid status {status!r}")
        if case_id in selected and status != "PASS":
            validation.error(f"{report_name}: required {scope} case {case_id} is {status}")
        if status == "PASS":
            for index, name in ((4, "terminal evidence"), (5, "forbidden effects"), (6, "cleanup")):
                if not meaningful(cells[index]):
                    validation.error(f"{report_name}: PASS {case_id} has no {name}")
            if row["tier"] == "A+B" and not (
                re.search(r"(?:^|[;\s])A\s*:", cells[4], re.I)
                and re.search(r"(?:^|[;\s])B\s*:", cells[4], re.I)
            ):
                validation.error(f"{report_name}: PASS {case_id} lacks reconciled A: and B: evidence")

    dependency_rows: list[list[str]] = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) == 6 and cells[0] not in {"Dependency", "---"}:
            dependency_rows.append(cells)
    if not dependency_rows:
        validation.error(f"{report_name}: Dependencies needs an explicit service row or none row")
    for cells in dependency_rows:
        if cells[1] not in {"yes", "no"}:
            validation.error(f"{report_name}: dependency {cells[0]!r} Required must be yes/no")
        if cells[1] == "yes":
            for index, name in ((2, "version/config"), (3, "health evidence"), (4, "failure route")):
                if not meaningful(cells[index]):
                    validation.error(f"{report_name}: dependency {cells[0]!r} lacks {name}")
            if cells[5] != "PASS":
                validation.error(f"{report_name}: required dependency {cells[0]!r} is not PASS")
    validate_final_gate(validation, text, report_name, scope)


def validate_final_gate(validation: Validation, text: str, report_name: str, scope: str) -> None:
    """Check only the Final Gate section, and only the criteria the scope may claim."""
    section = re.search(r"^##\s+Final Gate\s*$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    gate = section.group(1) if section else ""
    if not gate.strip():
        validation.error(f"{report_name}: Final Gate section is empty")
        return

    def checked(marker: str) -> bool:
        return bool(re.search(rf"^- \[[xX]\].*{re.escape(marker)}", gate, re.M))

    def present(marker: str) -> bool:
        return bool(re.search(rf"^- \[[ xX]\].*{re.escape(marker)}", gate, re.M))

    for marker in COMMON_GATE_MARKERS:
        if not checked(marker):
            validation.error(f"{report_name}: Final Gate is missing checked criterion {marker!r}")
    for marker in FULL_GATE_MARKERS:
        if not present(marker):
            validation.error(f"{report_name}: Final Gate is missing full-run criterion {marker!r}")
        elif scope == "full":
            if not checked(marker):
                validation.error(
                    f"{report_name}: Final Gate is missing checked criterion {marker!r}"
                )
        elif checked(marker):
            validation.error(
                f"{report_name}: scope={scope} must not claim full-run criterion {marker!r}"
            )
    # Known criteria are already reported above; this only catches extra unchecked items.
    known = COMMON_GATE_MARKERS + FULL_GATE_MARKERS
    for line in gate.splitlines():
        if not line.startswith("- [ ]"):
            continue
        if not any(marker in line for marker in known):
            validation.error(f"{report_name}: Final Gate item is unchecked: {line.strip()}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan_dir", type=Path)
    parser.add_argument("--scope", choices=("design", "smoke", "impact", "full"), default="design")
    parser.add_argument("--report", help="Report path relative to plan_dir")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    validation = Validation(args.plan_dir.resolve())
    if args.scope != "design" and not args.report:
        validation.error(f"scope={args.scope} requires --report")
    case_paths, blocks = collect_cases(validation)
    validate_case_blocks(validation, blocks)
    rows, manifest = validate_manifest(validation, case_paths, blocks)
    included = validate_surfaces(validation, manifest)
    validate_traceability(validation, manifest, included)
    validate_scenarios(validation, manifest, included)
    validate_decisions(validation)
    validate_runner_contracts(validation)
    if args.report:
        validate_report(validation, rows, args.report, args.scope)

    for error in validation.errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if validation.errors:
        print(f"Validation failed with {len(validation.errors)} error(s).", file=sys.stderr)
        return 1
    print(
        f"Validated {len(manifest)} cases, {len(included)} included surfaces "
        f"for scope={args.scope}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
