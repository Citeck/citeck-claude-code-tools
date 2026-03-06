#!/usr/bin/env python3
"""Update an issue in Citeck Project Tracker."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from lib.records_api import records_mutate, RecordsApiError
from lib.auth import get_username

SOURCE_ID = "emodel/ept-issue"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Update a Citeck Project Tracker issue")
    parser.add_argument("--issue", required=True, help="Issue ID (e.g., EPT-123 or full record ref)")
    parser.add_argument("--status", help="New status (e.g., in-progress, done)")
    parser.add_argument("--assignee", help="New assignee (e.g., person/username)")
    parser.add_argument("--priority", help="New priority (e.g., 200_high)")
    parser.add_argument("--summary", help="New summary/title")
    parser.add_argument("--description", help="New description")
    parser.add_argument("--dry-run", action="store_true", help="Preview without updating")
    return parser.parse_args(argv)


def resolve_issue_ref(issue_id):
    """Convert a short issue ID to a full record reference."""
    if "/" in issue_id and "@" in issue_id:
        return issue_id
    return f"{SOURCE_ID}@{issue_id}"


def resolve_workspace(issue_id):
    """Extract workspace key from issue ID (e.g., COREDEV-66 -> COREDEV)."""
    ref = resolve_issue_ref(issue_id)
    local_id = ref.split("@", 1)[-1]  # e.g., "COREDEV-66"
    parts = local_id.rsplit("-", 1)
    if len(parts) == 2:
        return parts[0]
    return local_id


def build_record(args):
    """Build the mutation record from CLI arguments."""
    attributes = {}

    if args.status:
        attributes["_state?str"] = args.status
    if args.assignee:
        assignee = args.assignee
        if assignee == "me":
            username = get_username()
            if not username:
                print("Error: Cannot resolve 'me' — username not found. Check auth config.", file=sys.stderr)
                sys.exit(1)
            assignee = username
        if not assignee.startswith("emodel/person@"):
            assignee = f"emodel/person@{assignee}"
        attributes["implementer?str"] = assignee
    if args.priority:
        attributes["priority?str"] = args.priority
    if args.summary:
        attributes["summary?str"] = args.summary
    if args.description:
        attributes["description?str"] = args.description

    if not attributes:
        raise ValueError("No attributes to update. Specify at least one of: --status, --assignee, --priority, --summary, --description")

    attributes["_workspace?str"] = resolve_workspace(args.issue)

    return {
        "id": resolve_issue_ref(args.issue),
        "attributes": attributes,
    }


def format_preview(record):
    """Format a record update as a human-readable preview."""
    lines = [
        "Update Preview:",
        f"  Issue: {record['id']}",
        "  Changes:",
    ]
    attr_labels = {
        "_state?str": "Status",
        "implementer?str": "Assignee",
        "priority?str": "Priority",
        "summary?str": "Summary",
        "description?str": "Description",
    }
    for key, value in record["attributes"].items():
        if key == "_workspace?str":
            continue
        label = attr_labels.get(key, key)
        lines.append(f"    {label}: {value}")
    lines.append("")
    lines.append("Mutation payload:")
    lines.append(json.dumps({"records": [record], "version": 1}, indent=2, ensure_ascii=False))
    return "\n".join(lines)


def main(argv=None):
    args = parse_args(argv)
    try:
        record = build_record(args)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print(format_preview(record))
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
        updated_id = result_records[0].get("id", "unknown")
        print(f"Updated issue: {updated_id}")
    else:
        print("Issue updated.")
    print()
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
