"""Structural and CLI tests for the citeck-test-feature skill."""

from __future__ import annotations

import csv
import importlib.util
import os
import re
from argparse import Namespace
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parent.parent / "skills" / "citeck-test-feature"
SCRIPTS_DIR = SKILL_DIR / "scripts"


def run_script(name: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / name), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def load_script_module(name: str):
    path = SCRIPTS_DIR / name
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_valid_plan(root: Path) -> Path:
    plan = root / "plan"
    (plan / "cases").mkdir(parents=True)
    (plan / "subagent-prompts").mkdir()
    (plan / "reports").mkdir()
    (plan / "cases" / "feature.md").write_text(
        textwrap.dedent(
            """\
            # Cases: feature

            ## F1. Complete journey
            **Kind:** journey  •  **Scopes:** smoke,impact,full  •  **Tier:** A+B  •  **Cluster:** 1  •
            **Tools:** `[HTTP]` `[RA]` `[PW]`  •  **Subagent:** tier-a + tier-b
            - **Trace:** SURF-1, Controller.
            - **Setup:** isolated fixture.
            - **Entry point:** supported UI.
            - **Steps:** submit and complete.
            - **Contract assertions:** exact HTTP statuses.
            - **Terminal oracle:** saved record reopens.
            - **Forbidden side effects:** no duplicate.
            - **Evidence:** HTTP, Records and UI.
            - **Cleanup:** fixture deleted.
            - **Alternative coverage:** scenario-matrix.tsv rows for Feature journey.
            """
        )
    )
    (plan / "subagent-prompts" / "tier-a-feature.md").write_text("Run F1 API evidence.\n")
    (plan / "subagent-prompts" / "tier-b-ui.md").write_text("Run and reconcile F1 UI evidence.\n")
    (plan / "case-manifest.tsv").write_text(
        "case_id\tcase_file\tkind\ttier\tcluster\trequired\tscopes\trunner_prompt\tdependencies\t"
        "resource_lock\tcapability\n"
        "F1\tcases/feature.md\tjourney\tA+B\t1\tyes\tsmoke,impact,full\t"
        "subagent-prompts/tier-a-feature.md,subagent-prompts/tier-b-ui.md\t"
        "none\tfixture-f1\tFeature journey\n"
    )
    (plan / "surface-inventory.tsv").write_text(
        "surface_id\tkind\tsource\toperation\tcapability\tincluded\tcase_ids\t"
        "exclusion_reason\towner\n"
        "SURF-1\trest\tController.kt\tPOST /api/feature\tFeature journey\tyes\tF1\t-\tteam\n"
    )
    (plan / "TRACEABILITY.md").write_text(
        "| Capability | Source evidence | Contract cases | Terminal journey | Guard cases | "
        "External oracle |\n"
        "|---|---|---|---|---|---|\n"
        "| Feature journey | SURF-1 | - | F1 | - | saved record reopened |\n"
    )
    (plan / "OPEN-DECISIONS.md").write_text(
        "| ID | Contract question | Current strict assumption | Owner | Blocking | Resolution |\n"
        "|---|---|---|---|---|---|\n"
    )
    dimensions = (
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
    )
    scenario_rows = [
        "capability\tdimension\tapplicable\trequired\tcase_ids\trationale"
    ]
    for dimension in dimensions:
        if dimension in {"happy", "cleanup"}:
            scenario_rows.append(
                f"Feature journey\t{dimension}\tyes\tyes\tF1\tcovered by terminal journey"
            )
        else:
            scenario_rows.append(
                f"Feature journey\t{dimension}\tno\tno\t-\tnot applicable to fixture"
            )
    (plan / "scenario-matrix.tsv").write_text("\n".join(scenario_rows) + "\n")
    return plan


def write_valid_report(
    plan: Path,
    status: str = "PASS",
    scope: str = "full",
    claim_full_gate: bool | None = None,
) -> Path:
    """Write a report whose Final Gate matches the scope unless a test overrides it."""
    report = plan / "reports" / "run.md"
    if claim_full_gate is None:
        claim_full_gate = scope == "full"
    full_mark = "x" if claim_full_gate else " "
    checked = "\n".join(
        (
            "- [x] validate-plan.py passes",
            "- [x] HEAD equals DEPLOYED_SHA",
            "- [x] All included surfaces are traced",
            "- [x] A+B cases contain reconciled evidence",
            "- [x] External effects were verified",
            "- [x] Cleanup restored the baseline",
            f"- [{full_mark}] Unit and required integration suites are green",
            f"- [{full_mark}] Every required full-run case is PASS",
        )
    )
    limitation = (
        ""
        if scope == "full"
        else f"**Scope limitation:** {scope} run does not claim full regression\n"
    )
    report.write_text(
        "# Report\n\n"
        f"**Scope:** `{scope}`  •  **Environment:** http://localhost (profile `test`, `dev`)\n"
        "**Source:** main @ `abcdef1`  •  **Deployed:** `abcdef1`\n\n"
        "**Provider/model/config:** local/test/default  •  **Dirty baseline:** clean\n"
        f"{limitation}\n"
        "## Dependencies\n\n"
        "| Dependency | Required | Version/config | Health evidence | Failure route | Status |\n"
        "|---|---|---|---|---|---|\n"
        "| records | yes | v1 | GET /health=200 | blocked | PASS |\n\n"
        "## Results\n\n"
        "| ID | Kind | Tier | Status | Terminal evidence | Forbidden effects | Cleanup |\n"
        "|---|---|---|---|---|---|---|\n"
        f"| F1 | journey | A+B | {status} | A: Records saved; B: UI reopened | "
        "no duplicate by query | fixture deleted |\n\n"
        f"## Final Gate\n\n{checked}\n"
    )
    return report


class TestScaffoldPlan(unittest.TestCase):
    def test_create_is_exclusive_and_resume_preserves_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            args = (
                "--project-root",
                str(project),
                "--issue",
                "COREDEV-999",
                "--feature",
                "Coverage",
                "--date",
                "2026-07-31",
                "--run-id",
                "r1",
            )
            first = run_script("scaffold-plan.py", *args)
            self.assertEqual(first.returncode, 0, first.stderr)
            plan = project / "docs" / "plans" / "2026-07-31-coredev-999-test-plan"
            for name in (
                "README.md",
                "case-manifest.tsv",
                "surface-inventory.tsv",
                "scenario-matrix.tsv",
                "TRACEABILITY.md",
                "OPEN-DECISIONS.md",
                "cases/feature.md",
                "subagent-prompts/tier-a-feature.md",
                "subagent-prompts/tier-b-ui.md",
                "reports/2026-07-31-r1.md",
            ):
                self.assertTrue((plan / name).is_file(), name)

            readme = plan / "README.md"
            readme.write_text("do not overwrite\n")
            duplicate = run_script("scaffold-plan.py", *args)
            self.assertEqual(duplicate.returncode, 2)
            resumed = run_script("scaffold-plan.py", *args, "--resume")
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertEqual(readme.read_text(), "do not overwrite\n")


class TestValidatePlan(unittest.TestCase):
    def test_valid_plan_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_valid_plan(Path(tmp))
            result = run_script("validate-plan.py", str(plan))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Validated 1 cases", result.stdout)

    def test_missing_terminal_oracle_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_valid_plan(Path(tmp))
            case_file = plan / "cases" / "feature.md"
            case_file.write_text(case_file.read_text().replace("**Terminal oracle:**", "**Result:**"))
            result = run_script("validate-plan.py", str(plan))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing required label **Terminal oracle:**", result.stderr)

    def test_a_plus_b_requires_both_runners(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_valid_plan(Path(tmp))
            manifest = plan / "case-manifest.tsv"
            manifest.write_text(
                manifest.read_text().replace(
                    "subagent-prompts/tier-a-feature.md,subagent-prompts/tier-b-ui.md",
                    "subagent-prompts/tier-a-feature.md",
                )
            )
            result = run_script("validate-plan.py", str(plan))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("A+B requires distinct tier-a and tier-b runner prompts", result.stderr)

    def test_traceability_requires_terminal_journey(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_valid_plan(Path(tmp))
            trace = plan / "TRACEABILITY.md"
            trace.write_text(trace.read_text().replace("| F1 | - |", "| - | F1 |"))
            result = run_script("validate-plan.py", str(plan))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("has no required journey in Terminal journey", result.stderr)

    def test_full_report_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_valid_plan(Path(tmp))
            report = write_valid_report(plan, "BLOCKED")
            blocked = run_script(
                "validate-plan.py",
                str(plan),
                "--scope",
                "full",
                "--report",
                "reports/run.md",
            )
            self.assertNotEqual(blocked.returncode, 0)
            self.assertIn("required full case F1 is BLOCKED", blocked.stderr)
            report.write_text(report.read_text().replace("| BLOCKED |", "| PASS |"))
            passed = run_script(
                "validate-plan.py",
                str(plan),
                "--scope",
                "full",
                "--report",
                "reports/run.md",
            )
            self.assertEqual(passed.returncode, 0, passed.stderr)

    def test_smoke_report_never_claims_the_full_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_valid_plan(Path(tmp))
            write_valid_report(plan, scope="smoke", claim_full_gate=True)
            claimed = run_script(
                "validate-plan.py", str(plan), "--scope", "smoke", "--report", "reports/run.md"
            )
            self.assertNotEqual(claimed.returncode, 0)
            self.assertIn("must not claim full-run criterion", claimed.stderr)

            write_valid_report(plan, scope="smoke")
            honest = run_script(
                "validate-plan.py", str(plan), "--scope", "smoke", "--report", "reports/run.md"
            )
            self.assertEqual(honest.returncode, 0, honest.stderr)

    def test_limited_scope_requires_a_scope_limitation(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_valid_plan(Path(tmp))
            report = write_valid_report(plan, scope="impact")
            report.write_text(
                report.read_text().replace(
                    "**Scope limitation:** impact run does not claim full regression\n", ""
                )
            )
            result = run_script(
                "validate-plan.py", str(plan), "--scope", "impact", "--report", "reports/run.md"
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("must state an explicit **Scope limitation:**", result.stderr)

    def test_full_report_requires_every_gate_criterion(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_valid_plan(Path(tmp))
            report = write_valid_report(plan)
            report.write_text(
                report.read_text().replace(
                    "- [x] Cleanup restored the baseline", "- [ ] Cleanup restored the baseline"
                )
            )
            result = run_script(
                "validate-plan.py", str(plan), "--scope", "full", "--report", "reports/run.md"
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing checked criterion 'Cleanup restored'", result.stderr)
            # One error per criterion, not one from each of the two gate checks.
            self.assertEqual(result.stderr.count("Cleanup restored"), 1, result.stderr)

    def test_extra_unchecked_gate_item_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_valid_plan(Path(tmp))
            report = write_valid_report(plan)
            report.write_text(
                report.read_text().replace(
                    "- [x] Cleanup restored the baseline",
                    "- [x] Cleanup restored the baseline\n- [ ] screenshots attached",
                )
            )
            result = run_script(
                "validate-plan.py", str(plan), "--scope", "full", "--report", "reports/run.md"
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Final Gate item is unchecked: - [ ] screenshots attached", result.stderr)

    def test_unchecked_boxes_outside_the_final_gate_are_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_valid_plan(Path(tmp))
            report = write_valid_report(plan)
            report.write_text(
                report.read_text().replace(
                    "## Final Gate",
                    "## Follow-up\n\n- [ ] file a defect for the slow response\n\n## Final Gate",
                )
            )
            result = run_script(
                "validate-plan.py", str(plan), "--scope", "full", "--report", "reports/run.md"
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_case_id_is_recognised_at_the_end_of_a_sentence(self):
        """Found road-testing the skill: `… and F1.` was read as a missing mention."""
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_valid_plan(Path(tmp))
            for name in ("tier-a-feature.md", "tier-b-ui.md"):
                (plan / "subagent-prompts" / name).write_text("Run the assigned case F1.\n")
            result = run_script("validate-plan.py", str(plan))
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_sub_case_id_does_not_count_as_the_parent_mention(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_valid_plan(Path(tmp))
            for name in ("tier-a-feature.md", "tier-b-ui.md"):
                (plan / "subagent-prompts" / name).write_text("Run only F1.2 here.\n")
            result = run_script("validate-plan.py", str(plan))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("does not mention exact case ID", result.stderr)

    def test_execution_scope_requires_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_valid_plan(Path(tmp))
            result = run_script("validate-plan.py", str(plan), "--scope", "full")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("scope=full requires --report", result.stderr)

    def test_pass_requires_evidence_and_matching_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_valid_plan(Path(tmp))
            report = write_valid_report(plan)
            text = report.read_text().replace("`abcdef1`\n", "`1234567`\n", 1)
            text = text.replace("A: Records saved; B: UI reopened", "-")
            report.write_text(text)
            result = run_script(
                "validate-plan.py", str(plan), "--scope", "full", "--report", "reports/run.md"
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("HEAD and DEPLOYED_SHA", result.stderr)
            self.assertIn("has no terminal evidence", result.stderr)

    def test_scenario_matrix_requires_every_dimension(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_valid_plan(Path(tmp))
            matrix = plan / "scenario-matrix.tsv"
            matrix.write_text(matrix.read_text().replace(
                "Feature journey\tconcurrency\tno\tno\t-\tnot applicable to fixture\n", ""
            ))
            result = run_script("validate-plan.py", str(plan))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing 'Feature journey'/concurrency", result.stderr)

    def test_traceability_rejects_wrong_capability(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_valid_plan(Path(tmp))
            trace = plan / "TRACEABILITY.md"
            trace.write_text(trace.read_text().replace("Feature journey", "Other capability"))
            result = run_script("validate-plan.py", str(plan))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing capability 'Feature journey'", result.stderr)

    def test_dependencies_must_be_known_and_acyclic(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_valid_plan(Path(tmp))
            manifest = plan / "case-manifest.tsv"
            manifest.write_text(manifest.read_text().replace("\tnone\tfixture", "\tF2\tfixture"))
            result = run_script("validate-plan.py", str(plan))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unknown dependencies ['F2']", result.stderr)

    def test_orphan_manifest_capability_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_valid_plan(Path(tmp))
            case_file = plan / "cases" / "feature.md"
            original = case_file.read_text()
            second = original[original.index("## F1."):].replace(
                "## F1. Complete journey", "## F2. Orphan journey", 1
            )
            case_file.write_text(original + "\n" + second)
            manifest = plan / "case-manifest.tsv"
            row = manifest.read_text().splitlines()[1].replace("F1\t", "F2\t", 1)
            row = row.replace("\tyes\t", "\tno\t", 1).replace("Feature journey", "Orphan capability")
            manifest.write_text(manifest.read_text() + row + "\n")
            prompt = plan / "subagent-prompts" / "tier-a-feature.md"
            prompt.write_text(prompt.read_text() + "Run F2.\n")
            prompt = plan / "subagent-prompts" / "tier-b-ui.md"
            prompt.write_text(prompt.read_text() + "Run F2.\n")
            result = run_script("validate-plan.py", str(plan))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("manifest capability 'Orphan capability' is missing for F2", result.stderr)

    def test_full_includes_dependency_closure(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_valid_plan(Path(tmp))
            # Reuse F1 as its own coverage case and add F2 as an execution prerequisite.
            case_file = plan / "cases" / "feature.md"
            original = case_file.read_text()
            second = original[original.index("## F1."):].replace(
                "## F1. Complete journey", "## F2. Prerequisite", 1
            )
            case_file.write_text(original + "\n" + second)
            manifest = plan / "case-manifest.tsv"
            lines = manifest.read_text().splitlines()
            lines[1] = lines[1].replace("\tnone\tfixture", "\tF2\tfixture")
            lines.append(lines[1].replace("F1\t", "F2\t", 1).replace("\tF2\tfixture", "\tnone\tfixture")
                         .replace("\tyes\t", "\tno\t", 1))
            manifest.write_text("\n".join(lines) + "\n")
            for name in ("tier-a-feature.md", "tier-b-ui.md"):
                prompt = plan / "subagent-prompts" / name
                prompt.write_text(prompt.read_text() + "Run F2.\n")
            trace = plan / "TRACEABILITY.md"
            trace.write_text(trace.read_text().replace("| - | F1 |", "| - | F1, F2 |"))
            report = write_valid_report(plan)
            report.write_text(report.read_text().replace(
                "| F1 | journey", "| F2 | journey | A+B | NOT_RUN | pending | pending | pending |\n| F1 | journey"
            ))
            result = run_script(
                "validate-plan.py", str(plan), "--scope", "full", "--report", "reports/run.md"
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("required full case F2 is NOT_RUN", result.stderr)

    def test_runner_channel_must_match_single_tier(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_valid_plan(Path(tmp))
            manifest = plan / "case-manifest.tsv"
            text = manifest.read_text().replace("\tA+B\t", "\tA\t")
            text = text.replace(
                "subagent-prompts/tier-a-feature.md,subagent-prompts/tier-b-ui.md",
                "subagent-prompts/tier-b-ui.md",
            )
            manifest.write_text(text)
            case_file = plan / "cases" / "feature.md"
            case_file.write_text(case_file.read_text().replace("**Tier:** A+B", "**Tier:** A"))
            result = run_script("validate-plan.py", str(plan))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Tier A requires only tier-a runner prompts", result.stderr)

    def test_included_surface_requires_a_full_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_valid_plan(Path(tmp))
            manifest = plan / "case-manifest.tsv"
            manifest.write_text(
                manifest.read_text().replace("\tyes\tsmoke,impact,full\t", "\tno\timpact\t")
            )
            result = run_script("validate-plan.py", str(plan))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("included surface needs a required full case", result.stderr)

    def test_unquoted_generic_action_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_valid_plan(Path(tmp))
            prompt = plan / "subagent-prompts" / "tier-a-feature.md"
            prompt.write_text(prompt.read_text() + '{ action: "confirm" }\n')
            result = run_script("validate-plan.py", str(plan))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("generic hardcoded action", result.stderr)

    def test_scaffold_rejects_unsafe_path_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_script(
                "scaffold-plan.py", "--project-root", tmp, "--issue", "X-1", "--feature", "X",
                "--date", "../../escape", "--run-id", "../run",
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("--date must be an ISO date", result.stderr)


class TestDiscoverSurfaces(unittest.TestCase):
    def test_discovers_backend_contract_categories(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            source = repo / "src" / "main" / "java" / "example"
            tools = source / "tools"
            tools.mkdir(parents=True)
            (source / "FeatureController.kt").write_text(
                '@ConfigurationProperties(prefix = "citeck.feature")\n'
                '@RequestMapping("/api")\n'
                '@GetMapping("/feature")\n'
                '@Scheduled(fixedDelay = 1000)\n'
                "fun firstJob() {}\n"
                '@Scheduled(fixedDelay = 1000)\n'
                "fun secondJob() {}\n"
                "class FeatureController\n"
            )
            (tools / "GenerateFeatureTool.kt").write_text("class GenerateFeatureTool\n")
            model = (
                repo
                / "src"
                / "main"
                / "resources"
                / "eapps"
                / "artifacts"
                / "model"
                / "type"
                / "feature.yml"
            )
            model.parent.mkdir(parents=True)
            model.write_text("id: feature\n")
            output = repo / "inventory.tsv"
            result = run_script(
                "discover-surfaces.py", str(repo), "--output", str(output)
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            with output.open(newline="") as stream:
                rows = list(csv.DictReader(stream, delimiter="\t"))
                kinds = {row["kind"] for row in rows}
            self.assertTrue({"rest", "config", "scheduler", "tool", "model"} <= kinds)
            self.assertIn("GET /api/feature", {row["operation"] for row in rows})
            self.assertEqual(sum(row["kind"] == "scheduler" for row in rows), 2)


class TestAsyncHttp(unittest.TestCase):
    def test_poll_requires_processing_then_terminal_result(self):
        module = load_script_module("async-http.py")
        responses = iter(((202, {"status": "processing"}), (200, {"result": {"ok": True}})))
        module.request_json = lambda method, url: next(responses)
        result = module.poll(
            Namespace(
                url="http://example/status/id",
                attempts=2,
                interval=0,
                processing_status=202,
                success_status=200,
                result_key="result",
            )
        )
        self.assertEqual(result["result"], {"ok": True})

    def test_auth_modes_are_mutually_exclusive(self):
        module = load_script_module("async-http.py")
        with mock.patch.dict(
            os.environ, {"BASIC_AUTH": "admin:admin", "BEARER_TOKEN": "token"}, clear=True
        ):
            with self.assertRaises(module.ContractError):
                module.auth_headers()


class TestSkillStaticContracts(unittest.TestCase):
    def test_no_stale_actions_or_destructive_restore(self):
        text = "\n".join(path.read_text() for path in SKILL_DIR.rglob("*.md"))
        self.assertNotRegex(text, r'"action"\s*:\s*"(confirm|reject|approve)"')
        self.assertNotRegex(text, r"git\s+(checkout|restore)\s+--")
        self.assertNotIn("$AUTH ", text)

    def test_skill_allows_profile_switch_tools(self):
        skill = (SKILL_DIR / "SKILL.md").read_text()
        self.assertIn("mcp__citeck__set_active_profile", skill)
        self.assertIn("mcp__citeck__set_records_profile", skill)
        self.assertIn("references/coverage-model.md", skill)

    def test_planning_templates_keep_placeholders_fail_closed(self):
        """A scaffolded plan must not pass validation with unfilled capability/owner fields."""
        templates = SKILL_DIR / "templates"
        for name in ("case-manifest.tsv", "surface-inventory.tsv", "scenario-matrix.tsv"):
            text = (templates / name).read_text()
            self.assertIn("<capability>", text, name)
            self.assertNotIn("Replace with capability", text, name)
        self.assertIn("<owner>", (templates / "surface-inventory.tsv").read_text())

    def test_skill_step_pointers_match_flow_headings(self):
        """If the flow tells the runner to read a reference at step N, the routing table must say N."""
        skill = (SKILL_DIR / "SKILL.md").read_text()
        table = {
            name: {int(number) for number in re.findall(r"\d+", column)}
            for name, column in re.findall(
                r"^\| `(references/[a-z0-9-]+\.md)`\s*\|([^|]*)\|", skill, re.M
            )
        }
        self.assertTrue(table, "routing table for references/* not found")

        flow = re.split(r"^### (\d+)\.", skill, flags=re.M)[1:]
        steps = {
            # A step body ends at the next flow step or the next top-level section.
            int(flow[index]): re.split(r"^## ", flow[index + 1], flags=re.M)[0]
            for index in range(0, len(flow), 2)
        }
        self.assertTrue(steps)
        for number in {n for row in table.values() for n in row}:
            self.assertIn(number, steps, "routing table points at a non-existent flow step")
        for number, body in steps.items():
            for name in set(re.findall(r"`?(references/[a-z0-9-]+\.md)`?", body)):
                self.assertIn(name, table, f"step {number} reads {name}, missing from the table")
                self.assertIn(
                    number,
                    table[name],
                    f"step {number} reads {name}, table says {sorted(table[name])}",
                )

    def test_tools_prescribed_by_runner_templates_are_allowlisted(self):
        allowlist = (SKILL_DIR / "references" / "environment.md").read_text()
        runner = (SKILL_DIR / "templates" / "subagent-tier-a.md").read_text()
        if "`jq`" in runner:
            self.assertIn("Bash(jq *)", allowlist)


if __name__ == "__main__":
    unittest.main()
