#!/usr/bin/env python3
"""Query releases in Citeck Project Tracker."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from lib.records_api import records_query, RecordsApiError
from lib.config import get_default_project

SOURCE_ID = "emodel/ecos-release-type"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Query Citeck Project Tracker releases")
    parser.add_argument("--project", help="Project/workspace key (e.g., COREDEV)")
    parser.add_argument("--status", help="Filter by status (e.g., new, in-progress, completed)")
    parser.add_argument("--limit", type=int, default=20, help="Max results (default: 20)")
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


def format_releases(records):
    """Format release records as a readable table."""
    if not records:
        return "No releases found."

    lines = []
    header = f"{'ID':<50} {'Name':<20} {'Status':<14} {'Start':<12} {'Release':<12} {'Implementer'}"
    lines.append(header)
    lines.append("-" * max(len(header), 120))
    for rec in records:
        attrs = rec.get("attributes", {})
        rec_id = rec.get("id", "")
        name = attrs.get("name", "")
        status_data = attrs.get("status", {})
        status = status_data.get("disp", status_data.get("value", "")) if isinstance(status_data, dict) else str(status_data)
        start = (attrs.get("startDate", "") or "")[:10]
        release = (attrs.get("releaseDate", "") or "")[:10]
        impl_data = attrs.get("implementer", {})
        implementer = impl_data.get("disp", "") if isinstance(impl_data, dict) else str(impl_data or "")
        lines.append(f"{rec_id:<50} {name:<20} {status:<14} {start:<12} {release:<12} {implementer}")
    return "\n".join(lines)


def main(argv=None):
    args = parse_args(argv)
    project = resolve_project(args.project)

    predicates = [{"t": "eq", "att": "_type", "val": "emodel/type@ecos-release-type"}]
    if args.status:
        predicates.append({"t": "eq", "att": "_status", "val": args.status})

    query = predicates[0] if len(predicates) == 1 else {"t": "and", "val": predicates}

    attributes = {
        "name": "releaseName?disp",
        "status": "_status{value:?str,disp:?disp}",
        "startDate": "startDate?disp",
        "releaseDate": "releaseDate?disp",
        "implementer": "implementer{disp:?disp,value:?assoc}",
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
    print(f"Found {len(records)} release{'s' if len(records) != 1 else ''} in {project}")
    print()
    print(format_releases(records))


if __name__ == "__main__":
    main()
