#!/usr/bin/env python3
"""Create an issue in Citeck Project Tracker."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from lib.records_api import records_mutate, records_query, records_load, RecordsApiError
from lib.config import get_credentials, get_default_project
from lib.auth import get_username

SOURCE_ID = "emodel/ept-issue"

TYPE_MAP = {
    "task": "ept-issue-task",
    "story": "ept-issue-story",
    "bug": "ept-issue-bug",
    "epic": "ept-issue-epic",
}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Create a Citeck Project Tracker issue")
    parser.add_argument("--project", help="Project key (e.g., EPT). Uses default if not specified.")
    parser.add_argument("--type", required=True, dest="issue_type",
                        choices=TYPE_MAP.keys(), help="Issue type")
    parser.add_argument("--summary", required=True, help="Issue summary/title")
    parser.add_argument("--description", default="", help="Issue description")
    parser.add_argument("--priority", default="300_medium", help="Priority (default: 300_medium)")
    parser.add_argument("--assignee", help="Assignee (e.g., person/username)")
    parser.add_argument("--sprint", help="Sprint reference")
    parser.add_argument("--component", action="append", help="Component reference (can be repeated)")
    parser.add_argument("--tags", action="append", help="Tag reference (can be repeated)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without creating")
    return parser.parse_args(argv)


def resolve_project_info(project_key):
    """Resolve a project key (e.g., ECOSDEV) to its ref and workspace key.

    Uses ?json to get all project attributes and extract 'key' for workspace.
    Returns (project_ref, workspace_key) tuple.
    """
    # First find the project by name
    result = records_query(
        source_id="emodel/project",
        query={"t": "eq", "att": "_name", "val": project_key},
        attributes={"id": "?id"},
        language="predicate",
        page={"maxItems": 1},
    )
    records = result.get("records", [])
    if not records:
        print(f"Error: Project '{project_key}' not found.", file=sys.stderr)
        sys.exit(1)
    project_ref = records[0]["attributes"]["id"]

    # Load project details to get the workspace key
    load_result = records_load([project_ref], ["?json"])
    load_records = load_result.get("records", [])
    if load_records:
        project_json = load_records[0].get("attributes", {}).get("?json", {})
        workspace_key = project_json.get("key", project_key)
    else:
        workspace_key = project_key

    return project_ref, workspace_key


def build_record(args, project_ref, workspace_key):
    """Build the mutation record from CLI arguments."""
    attributes = {
        "type?str": TYPE_MAP[args.issue_type],
        "_workspace?str": workspace_key,
        "_state?str": "submitted",
        "link-project:project?str": project_ref,
        "summary?str": args.summary,
        "description?str": args.description or "",
        "priority?str": args.priority,
    }

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

    if args.sprint:
        sprint = args.sprint
        if not sprint.startswith("emodel/ept-sprint@"):
            sprint = f"emodel/ept-sprint@{sprint}"
        attributes["sprint?assoc"] = [sprint]

    if args.component:
        components = []
        for c in args.component:
            if not c.startswith("emodel/ept-components@"):
                c = f"emodel/ept-components@{c}"
            components.append(c)
        attributes["components?assoc"] = components

    if args.tags:
        tags = []
        for t in args.tags:
            if not t.startswith("emodel/ept-tags@"):
                t = f"emodel/ept-tags@{t}"
            tags.append(t)
        attributes["tags?assoc"] = tags

    return {
        "id": f"{SOURCE_ID}@",
        "attributes": attributes,
    }


def format_preview(record):
    """Format a record as a human-readable preview."""
    attrs = record["attributes"]
    lines = [
        "Issue Preview:",
        f"  Type:        {attrs.get('type?str', 'unknown')}",
        f"  Project:     {attrs.get('_workspace?str', 'unknown')}",
        f"  Summary:     {attrs.get('summary?str', '')}",
        f"  Description: {attrs.get('description?str', '') or '(none)'}",
        f"  Priority:    {attrs.get('priority?str', '')}",
    ]
    if "implementer?str" in attrs:
        lines.append(f"  Assignee:    {attrs['implementer?str']}")
    if "sprint?assoc" in attrs:
        lines.append(f"  Sprint:      {attrs['sprint?assoc']}")
    if "components?assoc" in attrs:
        lines.append(f"  Components:  {attrs['components?assoc']}")
    if "tags?assoc" in attrs:
        lines.append(f"  Tags:        {attrs['tags?assoc']}")
    lines.append("")
    lines.append("Mutation payload:")
    lines.append(json.dumps({"records": [record], "version": 1}, indent=2, ensure_ascii=False))
    return "\n".join(lines)


def main(argv=None):
    args = parse_args(argv)
    project_key = args.project or get_default_project()
    if not project_key:
        print("Error: --project is required (no default project set). "
              "Use manage_projects.py --set-default to set one.", file=sys.stderr)
        sys.exit(1)
    project_ref, workspace_key = resolve_project_info(project_key)
    record = build_record(args, project_ref, workspace_key)

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
        created_id = result_records[0].get("id", "unknown")
        print(f"Created issue: {created_id}")
        creds = get_credentials()
        if creds:
            base_url = creds["url"].rstrip("/")
            print(f"Link: {base_url}/v2/dashboard?recordRef={created_id}")
    else:
        print("Issue created.")
    print()
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
