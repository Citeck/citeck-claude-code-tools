#!/usr/bin/env python3
"""Query issues in Citeck Project Tracker."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from lib.records_api import records_query, records_load, RecordsApiError
from lib.auth import get_username, AuthError
from lib.config import get_default_project, get_credentials

SOURCE_ID = "emodel/ept-issue"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Query Citeck Project Tracker issues")
    parser.add_argument("--project", help="Project/workspace key (e.g., EPT)")
    parser.add_argument("--status", help="Filter by status (e.g., in-progress)")
    parser.add_argument("--assignee", help="Filter by assignee (username or 'me')")
    parser.add_argument("--type", dest="issue_type", help="Filter by type: task, story, bug, epic")
    parser.add_argument("--sprint", help="Filter by sprint (full ref e.g. emodel/ept-sprint@UUID)")
    parser.add_argument("--limit", type=int, default=20, help="Max issues to return (default: 20)")
    parser.add_argument("--sort", default="_created", help="Sort attribute (default: _created)")
    parser.add_argument("--asc", action="store_true", help="Sort ascending (default: descending)")
    parser.add_argument("--json", dest="raw_json", help="Raw JSON request body (bypasses all other args)")
    parser.add_argument("--record", help="Load attributes for a specific record ID (e.g., emodel/ept-issue@EPT-123)")
    parser.add_argument("--attrs", help="Comma-separated attributes to load with --record (default: ?json)")
    return parser.parse_args(argv)


TYPE_MAP = {
    "task": "emodel/type@ept-issue-task",
    "story": "emodel/type@ept-issue-story",
    "bug": "emodel/type@ept-issue-bug",
    "epic": "emodel/type@ept-issue-epic",
}


def resolve_assignee(assignee_arg):
    """Resolve assignee argument, supporting 'me' shorthand."""
    if assignee_arg == "me":
        try:
            username = get_username()
        except AuthError:
            username = None
        if not username:
            print("Warning: Could not determine current user for --assignee me", file=sys.stderr)
            return None
        return username
    return assignee_arg


def build_query(args):
    """Build predicate query from CLI arguments."""
    predicates = []

    if args.status:
        predicates.append({"t": "eq", "att": "_status", "val": args.status})

    if args.assignee:
        assignee = args.assignee
        if not assignee.startswith("emodel/person@"):
            assignee = f"emodel/person@{assignee}"
        predicates.append({"att": "implementer", "t": "contains", "val": [assignee]})

    if args.issue_type:
        type_id = TYPE_MAP.get(args.issue_type)
        if not type_id:
            print(f"Error: Unknown issue type '{args.issue_type}'. Valid: {', '.join(TYPE_MAP.keys())}", file=sys.stderr)
            sys.exit(1)
        predicates.append({"t": "eq", "att": "_type", "val": type_id})

    if args.sprint:
        predicates.append({"t": "eq", "att": "sprint", "val": args.sprint})

    if len(predicates) == 0:
        return {}
    if len(predicates) == 1:
        return predicates[0]
    return {"t": "and", "val": predicates}


def format_issues(records):
    """Format issue records as a readable table."""
    if not records:
        return "No issues found."

    lines = []
    header = f"{'ID':<16} {'Type':<8} {'Status':<14} {'Priority':<12} {'Assignee':<20} {'Summary'}"
    lines.append(header)
    lines.append("-" * max(len(header), 100))
    for rec in records:
        attrs = rec.get("attributes", rec)
        issue_id = attrs.get("id", "")
        issue_type = attrs.get("type", "").replace("emodel/type@ept-issue-", "")
        status = attrs.get("status", "")
        priority = attrs.get("priority", "")
        assignee = attrs.get("assignee", "") or ""
        summary = attrs.get("summary", "")
        lines.append(f"{issue_id:<16} {issue_type:<8} {status:<14} {priority:<12} {assignee:<20} {summary}")
    return "\n".join(lines)


def main(argv=None):
    args = parse_args(argv)

    # Mode 1: Load attributes for a specific record by ID
    if args.record:
        attrs = args.attrs.split(",") if args.attrs else ["?json"]
        try:
            result = records_load([args.record], attrs)
        except RecordsApiError as e:
            print(f"Error: {e}", file=sys.stderr)
            if e.response_body:
                print(f"Response: {e.response_body}", file=sys.stderr)
            sys.exit(1)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    # Mode 2: Raw JSON request body
    if args.raw_json:
        try:
            body = json.loads(args.raw_json)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON: {e}", file=sys.stderr)
            sys.exit(1)
        from lib.records_api import request, QUERY_PATH
        try:
            result = request(QUERY_PATH, body)
        except RecordsApiError as e:
            print(f"Error: {e}", file=sys.stderr)
            if e.response_body:
                print(f"Response: {e.response_body}", file=sys.stderr)
            sys.exit(1)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    # Mode 3: Structured query via CLI args
    if args.assignee:
        args.assignee = resolve_assignee(args.assignee)

    query = build_query(args)

    project = args.project or get_default_project()
    workspaces = [project] if project else None
    sort_by = [{"attribute": args.sort, "ascending": args.asc}]

    attributes = {
        "id": "?localId",
        "summary": "summary?str",
        "status": "_status?str",
        "assignee": "implementer?disp",
        "priority": "priority?str",
        "type": "_type?id",
    }

    try:
        result = records_query(
            source_id=SOURCE_ID,
            query=query if query else None,
            attributes=attributes,
            language="predicate",
            page={"maxItems": args.limit},
            sort_by=sort_by,
            workspaces=workspaces,
        )
    except RecordsApiError as e:
        print(f"Error: {e}", file=sys.stderr)
        if e.response_body:
            print(f"Response: {e.response_body}", file=sys.stderr)
        sys.exit(1)

    records = result.get("records", [])
    print(f"Found {len(records)} issue{'s' if len(records) != 1 else ''}")
    print()
    print(format_issues(records))

    # Output base URL for link generation
    creds = get_credentials()
    if creds and creds.get("url"):
        print(f"\nBase URL: {creds['url']}")


if __name__ == "__main__":
    main()
