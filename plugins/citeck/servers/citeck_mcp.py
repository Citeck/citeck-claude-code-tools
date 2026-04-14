"""Citeck ECOS MCP server for Claude Code."""

import mimetypes
import os
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from fastmcp import FastMCP

# Add parent directory to path so lib/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.auth import AuthError, get_auth_header, validate_connection, get_username
from lib.config import (
    get_credentials, get_active_profile,
    get_projects, get_default_project, set_default_project,
    ConfigError,
)
from lib.records_api import (
    records_query as lib_records_query,
    records_load as lib_records_load,
    records_mutate as lib_records_mutate,
    RecordsApiError,
)

# In-memory cache for fetched projects, keyed by (profile, url).
# Avoids redundant API calls within a session. Note: if credentials
# change for the same profile+url (e.g. different user), call with
# fetch=true to refresh.
_projects_cache: dict[tuple[str, str], list[dict]] = {}

mcp = FastMCP(
    "citeck",
    instructions=(
        "Citeck ECOS platform tools — query records, manage tracker issues.\n\n"
        "When investigating a specific issue (e.g. by ID like COREDEV-3703):\n"
        "1. Use search_issues to get issue details.\n"
        "2. Use query_comments to fetch comments — they contain important context, "
        "discussion, and decisions. Images are auto-downloaded to local files.\n"
        "3. If comments contain images (non-empty 'images' list with 'path' values), "
        "AUTOMATICALLY read each downloaded file with the Read tool to understand "
        "screenshots and visual context. Do this without asking the user — images "
        "in bug reports are essential for understanding the issue."
    ),
)


def _get_config_dir() -> str | None:
    """Return config directory. Overridable in tests."""
    return None


@mcp.tool
def ping() -> dict:
    """Health-check: returns {ok: true} to verify the MCP server is running."""
    return {"ok": True}


@mcp.tool
def test_connection() -> dict:
    """Test connection to Citeck ECOS.

    Validates credentials by attempting authentication.
    Returns connection status with method, username, and server URL.
    """
    config_dir = _get_config_dir()
    try:
        profile = get_active_profile(config_dir)
        creds = get_credentials(profile, config_dir)
        if creds is None:
            return {
                "ok": False,
                "error": f"No credentials found for profile '{profile}'. "
                         "Run 'citeck:citeck-auth' to configure.",
            }

        result = validate_connection(profile=profile, config_dir=config_dir)

        if result["ok"]:
            username = get_username(profile=profile, config_dir=config_dir)
            result["username"] = username
            result["url"] = creds["url"]

        return result
    except AuthError as e:
        return {"ok": False, "error": str(e)}
    except ConfigError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


@mcp.tool
def records_query(
    source_id: str | None = None,
    query: dict | None = None,
    attributes: dict | None = None,
    record_ids: list[str] | None = None,
    language: str = "",
    page: dict | None = None,
    sort_by: list[dict] | None = None,
    workspaces: list[str] | None = None,
) -> dict:
    """Query or load records from Citeck ECOS Records API.

    Two modes:
    - Query by predicate: provide source_id (and optionally query, language, page, workspaces)
    - Load by IDs: provide record_ids

    Note: for issue queries, the assignee field is called "implementer" (not "assignee").
    Example predicate: {"t": "contains", "att": "implementer", "val": ["emodel/person@username"]}

    Args:
        source_id: Records source ID (e.g. "emodel/ept-issue"). Required for query mode.
        query: Query predicate dict (e.g. {"t": "eq", "a": "_status", "v": "open"}).
        attributes: Dict of attribute aliases to attribute names (e.g. {"summary": "summary?str"}).
        record_ids: List of record IDs to load directly (e.g. ["emodel/ept-issue@uuid"]).
        language: Query language (default: "").
        page: Pagination dict with 'maxItems' and/or 'skipCount'.
        sort_by: List of sort dicts (e.g. [{"attribute": "_created", "ascending": false}]).
        workspaces: List of workspace/project keys to filter by.
    """
    config_dir = _get_config_dir()

    if not source_id and not record_ids:
        return {
            "ok": False,
            "error": "Either source_id or record_ids must be provided.",
        }

    try:
        if record_ids:
            response = lib_records_load(
                record_ids=record_ids,
                attributes=attributes,
                config_dir=config_dir,
            )
        else:
            response = lib_records_query(
                source_id=source_id,
                query=query,
                attributes=attributes,
                language=language,
                page=page,
                sort_by=sort_by,
                workspaces=workspaces,
                config_dir=config_dir,
            )
        return {"ok": True, **response}
    except RecordsApiError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


@mcp.tool
def records_mutate(
    records: list[dict],
    version: int = 1,
) -> dict:
    """Create or update records via Citeck ECOS Records API.

    Args:
        records: List of record dicts, each with 'id' and 'attributes'.
                 For create: use empty ID suffix (e.g. "emodel/ept-issue@").
                 For update: use full record ID (e.g. "emodel/ept-issue@uuid").
                 Attributes MUST have type suffixes (e.g. "summary?str", "_state?str").
                 "_workspace?str" is MANDATORY for both create and update.
        version: API version (default: 1).
    """
    config_dir = _get_config_dir()

    if not records:
        return {
            "ok": False,
            "error": "Records list must not be empty.",
        }

    try:
        profile = get_active_profile(config_dir)
        creds = get_credentials(profile, config_dir)
        server_url = creds["url"].rstrip("/") if creds else None
        response = lib_records_mutate(
            records=records,
            version=version,
            profile=profile,
            config_dir=config_dir,
        )
        return {"ok": True, "profile": profile, "server": server_url, **response}
    except RecordsApiError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


@mcp.tool
def list_projects(
    fetch: bool = False,
) -> dict:
    """List projects and optionally fetch available projects from Citeck.

    Args:
        fetch: If true, query the Citeck API for all available projects and cache them.
    """
    config_dir = _get_config_dir()

    try:
        # Determine active profile and URL for cache key
        profile = get_active_profile(config_dir)
        creds = get_credentials(profile, config_dir)
        cache_url = creds["url"] if creds else ""
        cache_key = (profile, cache_url)

        # Fetch from API if requested
        if fetch:
            response = lib_records_query(
                source_id="emodel/project",
                query={},
                attributes={
                    "key": "_name?str",
                    "name": "_disp?disp",
                    "type": "_type?id",
                },
                language="predicate",
                page={"maxItems": 100},
                profile=profile,
                config_dir=config_dir,
            )
            fetched = []
            for rec in response.get("records", []):
                attrs = rec.get("attributes", {})
                fetched.append({
                    "key": attrs.get("key", ""),
                    "name": attrs.get("name", ""),
                    "type": attrs.get("type", ""),
                })
            _projects_cache[cache_key] = fetched

        # Build result using the same profile snapshot
        result = {
            "ok": True,
            "projects": get_projects(profile=profile, config_dir=config_dir),
            "default_project": get_default_project(profile=profile, config_dir=config_dir),
        }

        # Include cached fetched projects for the active profile+url
        cached = _projects_cache.get(cache_key, [])
        if cached:
            result["fetched_projects"] = list(cached)

        return result
    except RecordsApiError as e:
        return {"ok": False, "error": str(e)}
    except ConfigError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


@mcp.tool
def set_project_default(
    project: str,
) -> dict:
    """Set the default project for Citeck operations.

    Auto-adds the project to the saved list if not already present.

    Args:
        project: Project key to set as default (e.g. "COREDEV").
    """
    if not project or not project.strip():
        return {"ok": False, "error": "Project key must not be empty"}

    config_dir = _get_config_dir()

    try:
        profile = get_active_profile(config_dir)
        set_default_project(project, profile=profile, config_dir=config_dir)
        return {
            "ok": True,
            "default_project": project,
            "projects": get_projects(profile=profile, config_dir=config_dir),
        }
    except ConfigError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


_ISSUE_SOURCE_ID = "emodel/ept-issue"


def _resolve_assignee(assignee: str | None, profile: str | None, config_dir: str | None) -> tuple[bool, str | None]:
    """Resolve assignee='me' to the current username. Returns (ok, value_or_error)."""
    if assignee != "me":
        return True, assignee
    try:
        resolved = get_username(profile=profile, config_dir=config_dir)
    except Exception:
        resolved = None
    if not resolved:
        return False, "Could not determine current user for assignee='me'."
    return True, resolved

_ISSUE_TYPE_SHORT_NAMES = {
    "task": "ept-issue-task",
    "story": "ept-issue-story",
    "bug": "ept-issue-bug",
    "epic": "ept-issue-epic",
}

_ISSUE_ATTRIBUTES = {
    "id": "?localId",
    "summary": "summary?str",
    "status": "_status?str",
    "assignee": "implementer?disp",
    "priority": "priority?str",
    "type": "_type?id",
}


def _build_issue_query(
    status: str | None = None,
    assignee: str | None = None,
    issue_type: str | None = None,
    sprint: str | None = None,
) -> dict:
    """Build a predicate query dict from filter parameters."""
    predicates = []

    if status:
        predicates.append({"t": "eq", "att": "_status", "val": status})

    if assignee:
        if not assignee.startswith("emodel/person@"):
            assignee = f"emodel/person@{assignee}"
        predicates.append({"att": "implementer", "t": "contains", "val": [assignee]})

    if issue_type:
        short = _ISSUE_TYPE_SHORT_NAMES.get(issue_type)
        if not short:
            valid = ", ".join(_ISSUE_TYPE_SHORT_NAMES.keys())
            raise ValueError(f"Unknown issue type '{issue_type}'. Valid: {valid}.")
        predicates.append({"t": "eq", "att": "_type", "val": f"emodel/type@{short}"})

    if sprint:
        predicates.append({"t": "eq", "att": "sprint", "val": sprint})

    if len(predicates) == 0:
        return {}
    if len(predicates) == 1:
        return predicates[0]
    return {"t": "and", "val": predicates}


def _format_issues(records: list[dict], base_url: str | None = None) -> list[dict]:
    """Extract and clean issue attributes from raw records."""
    issues = []
    for rec in records:
        attrs = rec.get("attributes", rec)
        record_ref = rec.get("id", "")
        issue_type = attrs.get("type", "")
        # Strip the type prefix for readability
        if issue_type.startswith("emodel/type@ept-issue-"):
            issue_type = issue_type.replace("emodel/type@ept-issue-", "")
        issue = {
            "id": attrs.get("id", ""),
            "summary": attrs.get("summary", ""),
            "status": attrs.get("status", ""),
            "assignee": attrs.get("assignee", "") or "",
            "priority": attrs.get("priority", ""),
            "type": issue_type,
        }
        if base_url and record_ref:
            issue["link"] = f"{base_url}/v2/dashboard?recordRef={record_ref}"
        issues.append(issue)
    return issues


@mcp.tool
def search_issues(
    project: str | None = None,
    status: str | None = None,
    assignee: str | None = None,
    type: str | None = None,
    sprint: str | None = None,
    limit: int = 20,
    sort: str = "_created",
    ascending: bool = False,
    raw_query: dict | None = None,
) -> dict:
    """Search issues in Citeck Project Tracker.

    Args:
        project: Project/workspace key (e.g. "COREDEV"). Uses default project if not set.
        status: Filter by status (e.g. "to-do", "in-progress", "done").
        assignee: Filter by assignee username. Use "me" to auto-resolve to current user.
        type: Filter by issue type: task, story, bug, epic.
        sprint: Filter by sprint (full ref e.g. "emodel/ept-sprint@UUID").
        limit: Max issues to return (default: 20).
        sort: Sort attribute (default: "_created").
        ascending: Sort ascending (default: false = descending).
        raw_query: Raw predicate query dict — bypasses status/assignee/type/sprint filters.
    """
    config_dir = _get_config_dir()

    try:
        # Snapshot active profile for consistent usage
        profile = get_active_profile(config_dir)

        # Build query
        if raw_query is not None:
            query = raw_query
        else:
            # Resolve assignee "me" only when using structured filters
            ok, resolved_assignee = _resolve_assignee(assignee, profile, config_dir)
            if not ok:
                return {"ok": False, "error": resolved_assignee}

            # Validate type
            if type and type not in _ISSUE_TYPE_SHORT_NAMES:
                valid = ", ".join(_ISSUE_TYPE_SHORT_NAMES.keys())
                return {
                    "ok": False,
                    "error": f"Unknown issue type '{type}'. Valid types: {valid}.",
                }
            query = _build_issue_query(
                status=status,
                assignee=resolved_assignee,
                issue_type=type,
                sprint=sprint,
            )

        # Resolve project/workspace
        proj = project or get_default_project(profile=profile, config_dir=config_dir)
        workspaces = [proj] if proj else None

        sort_by = [{"attribute": sort, "ascending": ascending}]

        response = lib_records_query(
            source_id=_ISSUE_SOURCE_ID,
            query=query if query else None,
            attributes=_ISSUE_ATTRIBUTES,
            language="predicate",
            page={"maxItems": limit},
            sort_by=sort_by,
            workspaces=workspaces,
            profile=profile,
            config_dir=config_dir,
        )

        records = response.get("records", [])
        base_url = None
        creds = get_credentials(profile, config_dir)
        if creds:
            base_url = creds["url"].rstrip("/")
        issues = _format_issues(records, base_url=base_url)

        result = {
            "ok": True,
            "count": len(issues),
            "issues": issues,
        }
        if "totalCount" in response:
            result["totalCount"] = response["totalCount"]
        if "hasMore" in response:
            result["hasMore"] = response["hasMore"]
        return result
    except ConfigError as e:
        return {"ok": False, "error": str(e)}
    except RecordsApiError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


def _resolve_project_info(project_key: str, profile: str | None = None, config_dir: str | None = None) -> tuple[str, str]:
    """Resolve a project key to (project_ref, workspace_key).

    Queries the project by name, then loads its JSON to extract the workspace key.
    Raises ValueError if the project is not found.
    """
    result = lib_records_query(
        source_id="emodel/project",
        query={"t": "eq", "att": "_name", "val": project_key},
        attributes={"id": "?id"},
        language="predicate",
        page={"maxItems": 1},
        profile=profile,
        config_dir=config_dir,
    )
    records = result.get("records", [])
    if not records:
        raise ValueError(f"Project '{project_key}' not found.")
    attrs = records[0].get("attributes", {})
    project_ref = attrs.get("id")
    if not project_ref:
        raise ValueError(f"Could not resolve project ref for '{project_key}'.")

    load_result = lib_records_load(
        record_ids=[project_ref],
        attributes=["?json"],
        profile=profile,
        config_dir=config_dir,
    )
    load_records = load_result.get("records", [])
    if load_records:
        project_json = load_records[0].get("attributes", {}).get("?json", {})
        workspace_key = project_json.get("key", project_key)
    else:
        workspace_key = project_key

    return project_ref, workspace_key


def _build_create_record(
    issue_type: str,
    summary: str,
    project_ref: str,
    workspace_key: str,
    description: str = "",
    priority: str = "300_medium",
    assignee: str | None = None,
    reporter: str | None = None,
    sprint: str | None = None,
    components: list[str] | None = None,
    tags: list[str] | None = None,
) -> dict:
    """Build a mutation record for issue creation."""
    attributes = {
        "type?str": _ISSUE_TYPE_SHORT_NAMES[issue_type],
        "_workspace?str": workspace_key,
        "_state?str": "submitted",
        "link-project:project?str": project_ref,
        "summary?str": summary,
        "description?str": description or "",
        "priority?str": priority,
    }

    if reporter:
        if not reporter.startswith("emodel/person@"):
            reporter = f"emodel/person@{reporter}"
        attributes["reporter?str"] = reporter

    if assignee:
        if not assignee.startswith("emodel/person@"):
            assignee = f"emodel/person@{assignee}"
        attributes["implementer?str"] = assignee

    if sprint:
        if not sprint.startswith("emodel/ept-sprint@"):
            sprint = f"emodel/ept-sprint@{sprint}"
        attributes["sprint?assoc"] = [sprint]

    if components:
        refs = []
        for c in components:
            if not c.startswith("emodel/ept-components@"):
                c = f"emodel/ept-components@{c}"
            refs.append(c)
        attributes["components?assoc"] = refs

    if tags:
        refs = []
        for t in tags:
            if not t.startswith("emodel/ept-tags@"):
                t = f"emodel/ept-tags@{t}"
            refs.append(t)
        attributes["tags?assoc"] = refs

    return {
        "id": f"{_ISSUE_SOURCE_ID}@",
        "attributes": attributes,
    }


@mcp.tool
def create_issue(
    type: str,
    summary: str = "",
    project: str | None = None,
    description: str = "",
    priority: str = "300_medium",
    assignee: str | None = None,
    sprint: str | None = None,
    components: list[str] | None = None,
    tags: list[str] | None = None,
    preview: bool = True,
) -> dict:
    """Create an issue in Citeck Project Tracker.

    IMPORTANT: Always call with preview=true first. Show the FULL preview to the user.
    Get explicit confirmation before calling with preview=false to actually create.

    Args:
        type: Issue type: task, story, bug, epic.
        summary: Issue summary/title in English, imperative mood (required).
        project: Project key (e.g. "COREDEV"). Uses default project if not set.
        description: Issue description in HTML format (Lexical editor). Use tags: <p>, <h2>, <h3>, <ul>/<li>, <ol>/<li>, <code>, <b>, <i>.
        priority: Priority (default: "300_medium"). Options: 100_critical, 200_high, 300_medium, 400_low.
        assignee: Assignee username. Use "me" to auto-resolve to current user.
        sprint: Sprint reference (UUID or full ref).
        components: List of component references.
        tags: List of tag references.
        preview: If true (default), returns preview without creating. Set false to actually create.

    Reporter is auto-set to the current user.
    """
    config_dir = _get_config_dir()

    try:
        # Snapshot active profile for consistent usage
        profile = get_active_profile(config_dir)

        # Validate required fields
        if not summary:
            return {"ok": False, "error": "Summary is required."}

        # Validate type
        if type not in _ISSUE_TYPE_SHORT_NAMES:
            valid = ", ".join(_ISSUE_TYPE_SHORT_NAMES.keys())
            return {"ok": False, "error": f"Unknown issue type '{type}'. Valid types: {valid}."}

        # Resolve project
        proj_key = project or get_default_project(profile=profile, config_dir=config_dir)
        if not proj_key:
            return {
                "ok": False,
                "error": "Project is required (no default project set). "
                         "Use set_project_default to set one.",
            }

        # Resolve assignee "me"
        ok, resolved_assignee = _resolve_assignee(assignee, profile, config_dir)
        if not ok:
            return {"ok": False, "error": resolved_assignee}

        # Resolve reporter (current user)
        try:
            reporter = get_username(profile=profile, config_dir=config_dir)
        except Exception:
            reporter = None

        # Resolve project info
        project_ref, workspace_key = _resolve_project_info(proj_key, profile=profile, config_dir=config_dir)

        # Build record
        record = _build_create_record(
            issue_type=type,
            summary=summary,
            project_ref=project_ref,
            workspace_key=workspace_key,
            description=description,
            priority=priority,
            assignee=resolved_assignee,
            reporter=reporter,
            sprint=sprint,
            components=components,
            tags=tags,
        )

        # Resolve server info for responses
        creds = get_credentials(profile, config_dir)
        server_url = creds["url"].rstrip("/") if creds else None

        # Preview mode
        if preview:
            return {
                "ok": True,
                "preview": True,
                "profile": profile,
                "server": server_url,
                "record": record,
            }

        # Actually create
        result = lib_records_mutate(
            records=[record],
            version=1,
            profile=profile,
            config_dir=config_dir,
        )

        result_records = result.get("records", [])
        if result_records:
            created_id = result_records[0].get("id", "unknown")
            response = {
                "ok": True,
                "id": created_id,
                "profile": profile,
                "server": server_url,
            }
            if server_url:
                response["link"] = f"{server_url}/v2/dashboard?recordRef={created_id}"
            return response
        else:
            return {"ok": True, "message": "Issue created."}

    except ConfigError as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except RecordsApiError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


def _resolve_issue_ref(issue_id: str) -> str:
    """Convert a short issue ID to a full record reference."""
    if "/" in issue_id and "@" in issue_id:
        return issue_id
    return f"{_ISSUE_SOURCE_ID}@{issue_id}"


def _resolve_workspace_from_issue(issue_id: str) -> str:
    """Extract workspace key from issue ID (e.g., COREDEV-66 -> COREDEV)."""
    ref = _resolve_issue_ref(issue_id)
    local_id = ref.split("@", 1)[-1]  # e.g., "COREDEV-66"
    parts = local_id.rsplit("-", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0]
    raise ValueError(
        f"Cannot extract workspace from issue ID '{issue_id}'. "
        "Expected format: PROJECT-NUMBER (e.g., COREDEV-66)."
    )


def _build_update_record(
    issue_id: str,
    status: str | None = None,
    assignee: str | None = None,
    priority: str | None = None,
    summary: str | None = None,
    description: str | None = None,
) -> dict:
    """Build a mutation record for issue update."""
    attributes: dict = {}

    if status is not None:
        attributes["_state?str"] = status
    if assignee is not None:
        if not assignee.startswith("emodel/person@"):
            assignee = f"emodel/person@{assignee}"
        attributes["implementer?str"] = assignee
    if priority is not None:
        attributes["priority?str"] = priority
    if summary is not None:
        attributes["summary?str"] = summary
    if description is not None:
        attributes["description?str"] = description

    if not attributes:
        raise ValueError(
            "No attributes to update. Specify at least one of: "
            "status, assignee, priority, summary, description."
        )

    attributes["_workspace?str"] = _resolve_workspace_from_issue(issue_id)

    return {
        "id": _resolve_issue_ref(issue_id),
        "attributes": attributes,
    }


@mcp.tool
def update_issue(
    issue: str,
    status: str | None = None,
    assignee: str | None = None,
    priority: str | None = None,
    summary: str | None = None,
    description: str | None = None,
    preview: bool = True,
) -> dict:
    """Update an issue in Citeck Project Tracker.

    IMPORTANT: Always call with preview=true first. Show the FULL preview to the user.
    Get explicit confirmation before calling with preview=false to actually update.

    Args:
        issue: Issue ID (e.g. "COREDEV-42") or full record ref with PROJECT-NUMBER local ID
               (e.g. "emodel/ept-issue@COREDEV-42"). UUID-based refs are not supported.
        status: New status (e.g. "in-progress", "done", "to-do").
        assignee: New assignee username. Use "me" to auto-resolve to current user.
        priority: New priority (e.g. "100_critical", "200_high", "300_medium", "400_low").
        summary: New summary/title.
        description: New description.
        preview: If true (default), returns preview without updating. Set false to actually update.
    """
    config_dir = _get_config_dir()

    try:
        # Snapshot active profile for consistent usage
        profile = get_active_profile(config_dir)

        # Resolve assignee "me"
        ok, resolved_assignee = _resolve_assignee(assignee, profile, config_dir)
        if not ok:
            return {"ok": False, "error": resolved_assignee}

        # Build record
        record = _build_update_record(
            issue_id=issue,
            status=status,
            assignee=resolved_assignee,
            priority=priority,
            summary=summary,
            description=description,
        )

        # Resolve server info for responses
        creds = get_credentials(profile, config_dir)
        server_url = creds["url"].rstrip("/") if creds else None

        # Preview mode
        if preview:
            return {
                "ok": True,
                "preview": True,
                "profile": profile,
                "server": server_url,
                "record": record,
            }

        # Actually update
        result = lib_records_mutate(
            records=[record],
            version=1,
            profile=profile,
            config_dir=config_dir,
        )

        result_records = result.get("records", [])
        if result_records:
            updated_id = result_records[0].get("id", "unknown")
            response = {
                "ok": True,
                "id": updated_id,
                "profile": profile,
                "server": server_url,
            }
            if server_url:
                response["link"] = f"{server_url}/v2/dashboard?recordRef={updated_id}"
            return response
        else:
            return {"ok": True, "message": "Issue updated."}

    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except ConfigError as e:
        return {"ok": False, "error": str(e)}
    except RecordsApiError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


def _format_metadata_records(records: list[dict]) -> list[dict]:
    """Extract and format metadata records (sprints, components, tags, releases)."""
    result = []
    for rec in records:
        attrs = rec.get("attributes", {})
        item = {"id": rec.get("id", ""), "name": attrs.get("name", "")}

        # Status (sprints, releases)
        status_data = attrs.get("status")
        if status_data is not None:
            if isinstance(status_data, dict):
                item["status"] = status_data.get("disp", status_data.get("value", ""))
            else:
                item["status"] = str(status_data)

        # Dates
        for date_field in ("startDate", "endDate", "releaseDate"):
            if date_field in attrs:
                item[date_field] = (attrs.get(date_field, "") or "")[:10]

        # Creator (components, tags)
        creator_data = attrs.get("creator")
        if creator_data is not None:
            if isinstance(creator_data, dict):
                item["creator"] = creator_data.get("disp", "")
            else:
                item["creator"] = str(creator_data)

        # Implementer (releases)
        impl_data = attrs.get("implementer")
        if impl_data is not None:
            if isinstance(impl_data, dict):
                item["implementer"] = impl_data.get("disp", "")
            else:
                item["implementer"] = str(impl_data or "")

        result.append(item)
    return result


# --- Metadata source configs ---

_METADATA_CONFIGS = {
    "sprints": {
        "source_id": "emodel/ept-sprint",
        "type_filter": "emodel/type@ept-sprint",
        "attributes": {
            "name": "_disp?disp",
            "status": "_status{value:?str,disp:?disp}",
            "startDate": "startDate?disp",
            "endDate": "endDate?disp",
            "created": "_created",
        },
        "has_status": True,
    },
    "components": {
        "source_id": "emodel/ept-components",
        "type_filter": "emodel/type@ept-components",
        "attributes": {
            "name": "name?disp",
            "creator": "_creator{id:?id,disp:?disp}",
            "created": "_created",
        },
        "has_status": False,
    },
    "tags": {
        "source_id": "emodel/ept-tags",
        "type_filter": "emodel/type@ept-tags",
        "attributes": {
            "name": "name?disp",
            "creator": "_creator{id:?id,disp:?disp}",
            "created": "_created",
        },
        "has_status": False,
    },
    "releases": {
        "source_id": "emodel/ecos-release-type",
        "type_filter": "emodel/type@ecos-release-type",
        "attributes": {
            "name": "releaseName?disp",
            "status": "_status{value:?str,disp:?disp}",
            "startDate": "startDate?disp",
            "releaseDate": "releaseDate?disp",
            "implementer": "implementer{disp:?disp,value:?assoc}",
            "created": "_created",
        },
        "has_status": True,
    },
}


def _query_metadata(
    entity_type: str,
    project: str | None = None,
    status: str | None = None,
    limit: int = 50,
    ascending: bool = False,
) -> dict:
    """Generic metadata query for sprints, components, tags, releases."""
    config_dir = _get_config_dir()
    cfg = _METADATA_CONFIGS[entity_type]

    try:
        # Snapshot active profile for consistent usage
        profile = get_active_profile(config_dir)

        proj = project or get_default_project(profile=profile, config_dir=config_dir)
        if not proj:
            return {
                "ok": False,
                "error": "Project is required (no default project set). "
                         "Use set_project_default to set one.",
            }

        predicates = [{"t": "eq", "att": "_type", "val": cfg["type_filter"]}]
        if status and cfg["has_status"]:
            predicates.append({"t": "eq", "att": "_status", "val": status})

        query = predicates[0] if len(predicates) == 1 else {"t": "and", "val": predicates}

        response = lib_records_query(
            source_id=cfg["source_id"],
            query=query,
            attributes=cfg["attributes"],
            language="predicate",
            page={"maxItems": limit},
            sort_by=[{"attribute": "_created", "ascending": ascending}],
            workspaces=[proj],
            profile=profile,
            config_dir=config_dir,
        )

        records = response.get("records", [])
        formatted = _format_metadata_records(records)

        result = {"ok": True, "total": len(formatted), "records": formatted}
        if "totalCount" in response:
            result["totalCount"] = response["totalCount"]
        if "hasMore" in response:
            result["hasMore"] = response["hasMore"]
        return result
    except ConfigError as e:
        return {"ok": False, "error": str(e)}
    except RecordsApiError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


@mcp.tool
def query_sprints(
    project: str | None = None,
    status: str | None = None,
    limit: int = 20,
    ascending: bool = False,
) -> dict:
    """Query sprints in Citeck Project Tracker.

    Args:
        project: Project/workspace key (e.g. "COREDEV"). Uses default project if not set.
        status: Filter by status (e.g. "new", "in-progress", "completed").
        limit: Max results (default: 20).
        ascending: Sort ascending by creation date (default: false).
    """
    return _query_metadata("sprints", project=project, status=status, limit=limit, ascending=ascending)


@mcp.tool
def query_components(
    project: str | None = None,
    limit: int = 50,
    ascending: bool = False,
) -> dict:
    """Query components in Citeck Project Tracker.

    Args:
        project: Project/workspace key (e.g. "COREDEV"). Uses default project if not set.
        limit: Max results (default: 50).
        ascending: Sort ascending by creation date (default: false).
    """
    return _query_metadata("components", project=project, limit=limit, ascending=ascending)


@mcp.tool
def query_tags(
    project: str | None = None,
    limit: int = 50,
    ascending: bool = False,
) -> dict:
    """Query tags in Citeck Project Tracker.

    Args:
        project: Project/workspace key (e.g. "COREDEV"). Uses default project if not set.
        limit: Max results (default: 50).
        ascending: Sort ascending by creation date (default: false).
    """
    return _query_metadata("tags", project=project, limit=limit, ascending=ascending)


@mcp.tool
def query_releases(
    project: str | None = None,
    status: str | None = None,
    limit: int = 20,
    ascending: bool = False,
) -> dict:
    """Query releases in Citeck Project Tracker.

    Args:
        project: Project/workspace key (e.g. "COREDEV"). Uses default project if not set.
        status: Filter by status (e.g. "new", "in-progress", "completed").
        limit: Max results (default: 20).
        ascending: Sort ascending by creation date (default: false).
    """
    return _query_metadata("releases", project=project, status=status, limit=limit, ascending=ascending)


# --- HTML stripping utility ---


class _HTMLStripper(HTMLParser):
    """Minimal HTML-to-text converter with image URL extraction."""

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._srcs: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "img":
            for name, value in attrs:
                if name == "src" and value:
                    self._srcs.append(value)

    def get_text(self) -> str:
        return " ".join(self._parts).strip()

    def get_image_srcs(self) -> list[str]:
        return list(self._srcs)


def _strip_html(text: str | None) -> str:
    """Strip HTML tags from a string and collapse whitespace."""
    if not text:
        return ""
    stripper = _HTMLStripper()
    stripper.feed(text)
    return re.sub(r"\s+", " ", stripper.get_text()).strip()


def _extract_image_urls(html: str | None, base_url: str | None = None) -> list[dict]:
    """Extract and resolve image URLs from an HTML string.

    Returns list of dicts with 'src' (original from HTML) and 'url' (resolved).
    """
    if not html:
        return []
    stripper = _HTMLStripper()
    stripper.feed(html)
    srcs = stripper.get_image_srcs()
    seen = set()
    result = []
    for src in srcs:
        if src in seen:
            continue
        seen.add(src)
        resolved = urllib.parse.urljoin(base_url.rstrip("/") + "/", src) if base_url else src
        result.append({"src": src, "url": resolved})
    return result


# --- Comments ---

_COMMENT_SOURCE_ID = "emodel/comment"

_COMMENT_ATTRIBUTES = {
    "text": "text",
    "created": "_created",
    "modified": "_modified",
    "creator": "_creator{authorityName:?localId,userName:?localId,displayName:?disp,firstName,lastName,avatarUrl:avatar.url}",
    "modifier": "_modifier{authorityName:?localId,userName:?localId,displayName:?disp,firstName,lastName}",
    "canEdit": "permissions._has.Write?bool",
    "edited": "edited!false",
    "tags": "tags[]{type,name}",
}


def _format_comments(records: list[dict], base_url: str | None = None) -> list[dict]:
    """Extract and clean comment attributes from raw records."""
    comments = []
    for rec in records:
        attrs = rec.get("attributes", {})

        creator_raw = attrs.get("creator")
        if isinstance(creator_raw, dict):
            creator = {
                "username": creator_raw.get("userName") or creator_raw.get("authorityName") or "",
                "displayName": creator_raw.get("displayName") or "",
                "firstName": creator_raw.get("firstName") or "",
                "lastName": creator_raw.get("lastName") or "",
                "avatarUrl": creator_raw.get("avatarUrl") or "",
            }
        else:
            creator = {"displayName": str(creator_raw or "")}

        modifier_raw = attrs.get("modifier")
        if isinstance(modifier_raw, dict):
            modifier = {
                "username": modifier_raw.get("userName") or modifier_raw.get("authorityName") or "",
                "displayName": modifier_raw.get("displayName") or "",
                "firstName": modifier_raw.get("firstName") or "",
                "lastName": modifier_raw.get("lastName") or "",
            }
        else:
            modifier = {"displayName": str(modifier_raw or "")}

        raw_text = attrs.get("text") or ""
        image_info = _extract_image_urls(raw_text, base_url)
        comments.append({
            "id": rec.get("id", ""),
            "text": _strip_html(raw_text),
            "textHtml": raw_text,
            "imageUrls": [img["url"] for img in image_info],
            "_image_info": image_info,
            "created": attrs.get("created") or "",
            "modified": attrs.get("modified") or "",
            "creator": creator,
            "modifier": modifier,
            "canEdit": attrs.get("canEdit", False),
            "edited": attrs.get("edited", False),
            "tags": attrs.get("tags") or [],
        })
    return comments


@mcp.tool
def query_comments(
    record_ref: str,
    limit: int = 50,
    skip_count: int = 0,
) -> dict:
    """Fetch comments for a Citeck ECOS record.

    Comments are sorted newest first. The 'text' field is plain text
    (HTML stripped); 'textHtml' preserves the original HTML.
    Images from comments are automatically downloaded to ~/.citeck/downloads/
    and returned as 'images' list with local file paths. Use the Read tool
    to view the downloaded images.

    Args:
        record_ref: Full record reference (e.g. "emodel/ept-issue@COREDEV-3703").
        limit: Max comments to return (default: 50).
        skip_count: Number of comments to skip for pagination (default: 0).
    """
    config_dir = _get_config_dir()

    if not record_ref or not record_ref.strip():
        return {"ok": False, "error": "record_ref must not be empty."}

    try:
        profile = get_active_profile(config_dir)

        response = lib_records_query(
            source_id=_COMMENT_SOURCE_ID,
            query={"t": "eq", "a": "record", "v": record_ref},
            attributes=_COMMENT_ATTRIBUTES,
            language="predicate",
            page={"skipCount": skip_count, "maxItems": limit},
            sort_by=[{"attribute": "_created", "ascending": False}],
            profile=profile,
            config_dir=config_dir,
        )

        records = response.get("records", [])
        base_url = None
        creds = get_credentials(profile, config_dir)
        if creds:
            base_url = creds["url"].rstrip("/")
        comments = _format_comments(records, base_url=base_url)

        # Auto-download images from comments and replace URLs with local paths
        if base_url:
            try:
                auth_header = get_auth_header(profile=profile, config_dir=config_dir)
                for comment in comments:
                    images = []
                    html = comment.get("textHtml", "")
                    for img in comment.pop("_image_info", []):
                        img_url = img["url"]
                        raw_src = img["src"]
                        try:
                            dl = _download_file(img_url, auth_header, base_url, config_dir)
                            images.append({"url": img_url, "path": dl["path"], "content_type": dl["content_type"]})
                            if dl["path"] and html:
                                # Try both decoded src and HTML-encoded version
                                html = html.replace(raw_src, dl["path"])
                                html_encoded_src = raw_src.replace("&", "&amp;")
                                if html_encoded_src != raw_src:
                                    html = html.replace(html_encoded_src, dl["path"])
                        except Exception:
                            images.append({"url": img_url, "path": None, "error": "download failed"})
                    comment["images"] = images
                    if html != comment.get("textHtml", ""):
                        comment["textHtml"] = html
            except Exception:
                # Auth failed — leave images empty, comments are still useful
                for comment in comments:
                    comment.pop("_image_info", None)
                    comment["images"] = []
        else:
            for comment in comments:
                comment.pop("_image_info", None)
                comment["images"] = []

        result: dict = {
            "ok": True,
            "count": len(comments),
            "comments": comments,
        }
        if "totalCount" in response:
            result["totalCount"] = response["totalCount"]
        if "hasMore" in response:
            result["hasMore"] = response["hasMore"]
        return result

    except RecordsApiError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


_EXT_OVERRIDES = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif"}


def _download_file(url: str, auth_header: str, base_url: str, config_dir: str | None) -> dict:
    """Download a file from Citeck and save to ~/.citeck/downloads/.

    Returns dict with 'path', 'content_type', 'size' on success.
    Raises on network/IO errors.
    """
    abs_url = urllib.parse.urljoin(base_url + "/", url) if not url.startswith("http") else url

    req = urllib.request.Request(
        abs_url,
        headers={"Authorization": auth_header},
        method="GET",
    )

    with urllib.request.urlopen(req, timeout=60) as resp:
        content_type = resp.headers.get("Content-Type", "application/octet-stream").split(";")[0].strip()
        ext = _EXT_OVERRIDES.get(content_type, mimetypes.guess_extension(content_type) or "")
        data = resp.read()

    downloads_dir = os.path.join(config_dir or os.path.expanduser("~/.citeck"), "downloads")
    os.makedirs(downloads_dir, exist_ok=True)

    tmp = tempfile.NamedTemporaryFile(dir=downloads_dir, suffix=ext, delete=False)
    try:
        tmp.write(data)
        tmp.flush()
        tmp_path = tmp.name
    finally:
        tmp.close()

    return {"path": tmp_path, "content_type": content_type, "size": len(data)}


@mcp.tool
def download_attachment(
    url: str,
) -> dict:
    """Download a file from Citeck via authenticated session and return its local path.

    Saves the file to ~/.citeck/downloads/. Use the Read tool with the returned
    path to view the file contents. Supports images, PDFs, and other binary files.

    Args:
        url: Attachment URL — absolute (https://...) or relative (/gateway/...).
             Relative URLs are resolved against the configured Citeck base URL.
    """
    config_dir = _get_config_dir()

    if not url or not url.strip():
        return {"ok": False, "error": "url must not be empty."}

    try:
        profile = get_active_profile(config_dir)
        creds = get_credentials(profile, config_dir)
        if creds is None:
            return {
                "ok": False,
                "error": f"No credentials found for profile '{profile}'. "
                         "Run 'citeck:citeck-auth' to configure.",
            }

        base_url = creds["url"].rstrip("/")
        auth_header = get_auth_header(profile=profile, config_dir=config_dir)
        result = _download_file(url, auth_header, base_url, config_dir)
        return {"ok": True, **result}

    except AuthError as e:
        return {"ok": False, "error": str(e)}
    except ConfigError as e:
        return {"ok": False, "error": str(e)}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code} {e.reason}"}
    except (urllib.error.URLError, OSError) as e:
        return {"ok": False, "error": f"Connection error: {e}"}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


if __name__ == "__main__":
    mcp.run()
