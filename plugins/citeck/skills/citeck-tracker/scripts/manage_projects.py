#!/usr/bin/env python3
"""Manage saved project preferences for Citeck Project Tracker."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from lib.config import (
    get_projects, get_default_project, set_default_project,
    add_project, remove_project, ConfigError,
)
from lib.records_api import records_query, RecordsApiError


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Manage saved Citeck project preferences")
    parser.add_argument("--list", action="store_true", help="List saved projects and default")
    parser.add_argument("--add", metavar="PROJECT", help="Add project key to saved list")
    parser.add_argument("--remove", metavar="PROJECT", help="Remove project key from saved list")
    parser.add_argument("--set-default", metavar="PROJECT", dest="set_default",
                        help="Set default project (auto-adds if not in list)")
    parser.add_argument("--fetch", action="store_true",
                        help="Fetch available projects from Citeck")
    return parser.parse_args(argv)


def fetch_projects():
    """Fetch all available projects from Citeck."""
    result = records_query(
        source_id="emodel/project",
        query={},
        attributes={
            "key": "_name?str",
            "name": "_disp?disp",
            "type": "_type?id",
        },
        language="predicate",
        page={"maxItems": 100},
        sort_by=[{"attribute": "_created", "ascending": False}],
    )
    return result.get("records", [])


def show_list():
    """Show saved projects and default."""
    projects = get_projects()
    default = get_default_project()
    result = {
        "projects": projects,
        "default_project": default,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


def main(argv=None):
    args = parse_args(argv)

    if args.fetch:
        try:
            records = fetch_projects()
        except RecordsApiError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        if not records:
            print("No projects found.")
            return
        print(f"Found {len(records)} project(s):\n")
        for rec in records:
            attrs = rec.get("attributes", {})
            key = attrs.get("key", "?")
            name = attrs.get("name", "?")
            print(f"  {key:<16} {name}")
        return

    if args.add:
        try:
            add_project(args.add)
        except ConfigError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        print(f"Added project: {args.add}")
        show_list()
        return

    if args.remove:
        try:
            remove_project(args.remove)
        except ConfigError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        print(f"Removed project: {args.remove}")
        show_list()
        return

    if args.set_default:
        try:
            set_default_project(args.set_default)
        except ConfigError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        print(f"Default project set to: {args.set_default}")
        show_list()
        return

    # Default: --list
    show_list()


if __name__ == "__main__":
    main()
