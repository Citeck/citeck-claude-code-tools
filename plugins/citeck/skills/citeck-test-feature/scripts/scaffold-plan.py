#!/usr/bin/env python3
"""Create an idempotent Citeck test-plan skeleton from skill templates."""

from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import sys
from pathlib import Path


TEMPLATE_MAP = {
    "plan-readme.md": "README.md",
    "case.md": "cases/feature.md",
    "report.md": "reports/{date}-{run_id}.md",
    "subagent-tier-a.md": "subagent-prompts/tier-a-feature.md",
    "subagent-tier-b.md": "subagent-prompts/tier-b-ui.md",
    "case-manifest.tsv": "case-manifest.tsv",
    "surface-inventory.tsv": "surface-inventory.tsv",
    "scenario-matrix.tsv": "scenario-matrix.tsv",
    "traceability.md": "TRACEABILITY.md",
    "open-decisions.md": "OPEN-DECISIONS.md",
}


def slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not normalized:
        raise ValueError(f"Cannot build a safe slug from {value!r}")
    return normalized


def render(text: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        text = text.replace(f"<{key}>", value)
    return text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--issue", required=True)
    parser.add_argument("--feature", required=True)
    parser.add_argument("--date", default=dt.date.today().isoformat())
    parser.add_argument("--run-id", default="r1")
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def validate_path_tokens(date: str, run_id: str) -> None:
    try:
        parsed = dt.date.fromisoformat(date)
    except ValueError as error:
        raise ValueError("--date must be an ISO date (YYYY-MM-DD)") from error
    if parsed.isoformat() != date:
        raise ValueError("--date must be an ISO date (YYYY-MM-DD)")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", run_id) or ".." in run_id:
        raise ValueError("--run-id must be a safe filename token")


def main() -> int:
    args = parse_args()
    try:
        validate_path_tokens(args.date, args.run_id)
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    templates = Path(__file__).resolve().parent.parent / "templates"
    plan_dir = (
        args.project_root.resolve()
        / "docs"
        / "plans"
        / f"{args.date}-{slug(args.issue)}-test-plan"
    )
    if plan_dir.exists() and not args.resume:
        print(f"ERROR: {plan_dir} already exists; use --resume or a new date/issue", file=sys.stderr)
        return 2
    plan_dir.mkdir(parents=True, exist_ok=True)

    values = {
        "DATE": args.date,
        "RUN_ID": args.run_id,
        "ISSUE": args.issue,
        "FEATURE": args.feature,
    }
    created: list[Path] = []
    skipped: list[Path] = []
    for template_name, destination_pattern in TEMPLATE_MAP.items():
        source = templates / template_name
        destination = plan_dir / destination_pattern.format(date=args.date, run_id=args.run_id)
        if destination.exists():
            skipped.append(destination)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix in {".md", ".tsv"}:
            destination.write_text(render(source.read_text(), values))
        else:
            shutil.copy2(source, destination)
        created.append(destination)

    print(f"Plan: {plan_dir}")
    for path in created:
        print(f"CREATE {path.relative_to(plan_dir)}")
    for path in skipped:
        print(f"KEEP   {path.relative_to(plan_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
