#!/usr/bin/env python3
"""Parse task.md and create an issue in Citeck Project Tracker."""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from lib.records_api import records_mutate, RecordsApiError

SOURCE_ID = "emodel/ept-issue"

TYPE_MAP = {
    "Ошибка": "ept-issue-bug",
    "История": "ept-issue-story",
    "Задача": "ept-issue-task",
}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Create a Citeck issue from task.md"
    )
    parser.add_argument(
        "--task-file", required=True,
        help="Path to task.md file"
    )
    parser.add_argument(
        "--project", required=True,
        help="Project key (e.g., EPT)"
    )
    parser.add_argument(
        "--priority", default="300_medium",
        help="Priority (default: 300_medium)"
    )
    parser.add_argument(
        "--assignee",
        help="Assignee (e.g., person/username)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview without creating"
    )
    return parser.parse_args(argv)


def parse_task_file(file_path):
    """Parse task.md and extract type, summary, and description.

    Expected format:
        **Тип:** <type>

        ## <Title>

        <Description>

    Returns:
        dict with keys: type, summary, description
    Raises:
        ValueError if the file format is invalid
    """
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract type from **Тип:** line
    type_match = re.search(r"\*\*Тип:\*\*\s*(.+)", content)
    if not type_match:
        raise ValueError(
            "Cannot find type line. Expected format: **Тип:** <type>"
        )
    task_type = type_match.group(1).strip()

    if task_type not in TYPE_MAP:
        raise ValueError(
            f"Unknown type '{task_type}'. "
            f"Expected one of: {', '.join(TYPE_MAP.keys())}"
        )

    # Extract title from ## heading
    title_match = re.search(r"^##\s+(.+)$", content, re.MULTILINE)
    if not title_match:
        raise ValueError(
            "Cannot find title. Expected format: ## <Title>"
        )
    summary = title_match.group(1).strip()

    # Extract description: everything after the ## title line
    title_end = title_match.end()
    description = content[title_end:].strip()

    return {
        "type": task_type,
        "summary": summary,
        "description": description,
    }


def build_record(parsed, project, priority="300_medium", assignee=None):
    """Build the mutation record from parsed task data."""
    attributes = {
        "type?str": TYPE_MAP[parsed["type"]],
        "_workspace?str": project,
        "summary?str": parsed["summary"],
        "description?str": parsed["description"],
        "priority?str": priority,
    }

    if assignee:
        if not assignee.startswith("emodel/person@"):
            assignee = f"emodel/person@{assignee}"
        attributes["implementer?str"] = assignee

    return {
        "id": f"{SOURCE_ID}@",
        "attributes": attributes,
    }


def format_preview(record, parsed_type):
    """Format a record as a human-readable preview."""
    attrs = record["attributes"]
    lines = [
        "Issue Preview:",
        f"  Type:        {parsed_type}  ->  {attrs['type?str']}",
        f"  Project:     {attrs['_workspace?str']}",
        f"  Summary:     {attrs['summary?str']}",
        f"  Priority:    {attrs['priority?str']}",
    ]
    if "implementer?str" in attrs:
        lines.append(f"  Assignee:    {attrs['implementer?str']}")

    desc = attrs.get("description?str", "")
    if desc:
        # Show first 3 lines of description
        desc_lines = desc.split("\n")[:3]
        lines.append(f"  Description: {desc_lines[0]}")
        for dl in desc_lines[1:]:
            lines.append(f"               {dl}")
        if len(desc.split("\n")) > 3:
            lines.append("               ...")

    lines.append("")
    lines.append("Mutation payload:")
    lines.append(json.dumps({"records": [record], "version": 1}, indent=2, ensure_ascii=False))
    return "\n".join(lines)


def main(argv=None):
    args = parse_args(argv)

    # Parse task.md
    try:
        parsed = parse_task_file(args.task_file)
    except (ValueError, FileNotFoundError, OSError) as e:
        print(f"Error reading task file: {e}", file=sys.stderr)
        sys.exit(1)

    record = build_record(
        parsed,
        project=args.project,
        priority=args.priority,
        assignee=args.assignee,
    )

    if args.dry_run:
        print(format_preview(record, parsed["type"]))
        return

    try:
        result = records_mutate([record])
    except RecordsApiError as e:
        print(f"Error: {e}", file=sys.stderr)
        if e.response_body:
            print(f"Response: {e.response_body}", file=sys.stderr)
        sys.exit(1)

    result_records = result.get("records", [])
    if result_records:
        created_id = result_records[0].get("id", "unknown")
        print(f"Created issue: {created_id}")
    else:
        print("Issue created.")
    print()
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
