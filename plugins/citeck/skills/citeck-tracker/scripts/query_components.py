#!/usr/bin/env python3
"""Query components in Citeck Project Tracker."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from lib.records_api import records_query, RecordsApiError
from lib.config import get_default_project

SOURCE_ID = "emodel/ept-components"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Query Citeck Project Tracker components")
    parser.add_argument("--project", help="Project/workspace key (e.g., COREDEV)")
    parser.add_argument("--limit", type=int, default=50, help="Max results (default: 50)")
    parser.add_argument("--asc", action="store_true", help="Sort ascending (default: descending)")
    return parser.parse_args(argv)


def resolve_project(project_arg):
    """Resolve project from arg or default config."""
    if project_arg:
        return project_arg
    default = get_default_project()
    if default:
        return default
    print("Error: --project is required (no default project set). "
          "Use manage_projects.py --set-default to set one.", file=sys.stderr)
    sys.exit(1)


def format_components(records):
    """Format component records as a readable table."""
    if not records:
        return "No components found."

    lines = []
    header = f"{'ID':<50} {'Name':<20} {'Creator':<25} {'Created'}"
    lines.append(header)
    lines.append("-" * max(len(header), 100))
    for rec in records:
        attrs = rec.get("attributes", {})
        rec_id = rec.get("id", "")
        name = attrs.get("name", "")
        creator_data = attrs.get("creator", {})
        creator = creator_data.get("disp", "") if isinstance(creator_data, dict) else str(creator_data)
        created = (attrs.get("created", "") or "")[:10]
        lines.append(f"{rec_id:<50} {name:<20} {creator:<25} {created}")
    return "\n".join(lines)


def main(argv=None):
    args = parse_args(argv)
    project = resolve_project(args.project)

    query = {"t": "eq", "att": "_type", "val": "emodel/type@ept-components"}

    attributes = {
        "name": "name?disp",
        "creator": "_creator{id:?id,disp:?disp}",
        "created": "_created",
    }

    try:
        result = records_query(
            source_id=SOURCE_ID,
            query=query,
            attributes=attributes,
            language="predicate",
            page={"maxItems": args.limit},
            sort_by=[{"attribute": "_created", "ascending": args.asc}],
            workspaces=[project],
        )
    except RecordsApiError as e:
        print(f"Error: {e}", file=sys.stderr)
        if e.response_body:
            print(f"Response: {e.response_body}", file=sys.stderr)
        sys.exit(1)

    records = result.get("records", [])
    print(f"Found {len(records)} component{'s' if len(records) != 1 else ''} in {project}")
    print()
    print(format_components(records))


if __name__ == "__main__":
    main()
