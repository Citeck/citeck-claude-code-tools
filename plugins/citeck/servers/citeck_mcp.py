"""Citeck ECOS MCP server for Claude Code."""

import mimetypes
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from fastmcp import FastMCP

# Add parent directory to path so lib/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.auth import AuthError, get_auth_header, validate_connection, get_username
from lib.config import (
    get_credentials, get_active_profile, get_profiles,
    set_active_profile as lib_set_active_profile,
    get_projects, get_default_project, set_default_project,
    get_docs_profile as lib_get_docs_profile,
    set_docs_profile as lib_set_docs_profile,
    clear_docs_profile,
    get_ept_profile as lib_get_ept_profile,
    set_ept_profile as lib_set_ept_profile,
    clear_ept_profile,
    get_records_profile as lib_get_records_profile,
    set_records_profile as lib_set_records_profile,
    clear_records_profile,
    resolve_ept_profile,
    resolve_records_profile,
    ConfigError,
)
from lib.records_api import (
    records_query as lib_records_query,
    records_load as lib_records_load,
    records_mutate as lib_records_mutate,
    RecordsApiError,
)
from lib.rag_api import (
    search_docs as lib_search_docs,
    resolve_docs_profile,
    RagApiError,
    DEFAULT_TOP_K as RAG_DEFAULT_TOP_K,
    DEFAULT_THRESHOLD as RAG_DEFAULT_THRESHOLD,
)


def _cleanup_old_downloads(max_age_days: int = 7) -> None:
    """Remove files under ~/.citeck/downloads/ older than max_age_days."""
    downloads_dir = os.path.expanduser("~/.citeck/downloads")
    if not os.path.isdir(downloads_dir):
        return
    cutoff = time.time() - max_age_days * 86400
    try:
        entries = os.listdir(downloads_dir)
    except OSError:
        return
    for name in entries:
        path = os.path.join(downloads_dir, name)
        try:
            if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                os.remove(path)
        except OSError:
            pass


_cleanup_old_downloads()

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
        "in bug reports are essential for understanding the issue.\n\n"
        "Multiple environments are supported via profiles. Use list_profiles to see "
        "configured environments and set_active_profile to switch between them — "
        "do NOT ask the user to invoke /citeck:citeck-auth just to switch.\n\n"
        "Specialized profiles can route specific tool groups to different environments:\n"
        "- ept_profile (set_ept_profile): task-tracker tools (search_issues, create_issue, "
        "update_issue, list_projects, query_sprints/components/tags/releases, query_comments, "
        "download_attachment).\n"
        "- records_profile (set_records_profile): plain records_query / records_mutate.\n"
        "- docs_profile (set_docs_profile): search_docs.\n"
        "Each falls back to active_profile when unset. Useful e.g. when the tracker is on "
        "production but records queries should hit a local Citeck."
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
            result["profile"] = profile

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
    profile: str | None = None,
) -> dict:
    """Query or load records from Citeck ECOS Records API.

    Two modes:
    - Query by predicate: provide source_id (and optionally query, language, page, workspaces)
    - Load by IDs: provide record_ids

    Routes through records_profile if set, otherwise the active profile.

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
        profile: Override the profile for this call only. Usually leave empty.
    """
    config_dir = _get_config_dir()

    if not source_id and not record_ids:
        return {
            "ok": False,
            "error": "Either source_id or record_ids must be provided.",
        }

    try:
        resolved, _ = resolve_records_profile(profile=profile, config_dir=config_dir)
        if record_ids:
            response = lib_records_load(
                record_ids=record_ids,
                attributes=attributes,
                profile=resolved,
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
                profile=resolved,
                config_dir=config_dir,
            )
        return {"ok": True, **response}
    except RecordsApiError as e:
        return {"ok": False, "error": str(e)}
    except ConfigError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


@mcp.tool
def records_mutate(
    records: list[dict],
    version: int = 1,
    profile: str | None = None,
) -> dict:
    """Create or update records via Citeck ECOS Records API.

    Routes through records_profile if set, otherwise the active profile.

    Args:
        records: List of record dicts, each with 'id' and 'attributes'.
                 For create: use empty ID suffix (e.g. "emodel/ept-issue@").
                 For update: use full record ID (e.g. "emodel/ept-issue@uuid").
                 Attributes MUST have type suffixes (e.g. "summary?str", "_state?str").
                 "_workspace?str" is MANDATORY for both create and update.
        version: API version (default: 1).
        profile: Override the profile for this call only. Usually leave empty.
    """
    config_dir = _get_config_dir()

    if not records:
        return {
            "ok": False,
            "error": "Records list must not be empty.",
        }

    try:
        resolved, creds = resolve_records_profile(profile=profile, config_dir=config_dir)
        server_url = creds["url"].rstrip("/")
        response = lib_records_mutate(
            records=records,
            version=version,
            profile=resolved,
            config_dir=config_dir,
        )
        return {"ok": True, "profile": resolved, "server": server_url, **response}
    except RecordsApiError as e:
        return {"ok": False, "error": str(e)}
    except ConfigError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


@mcp.tool
def list_projects(
    fetch: bool = False,
    profile: str | None = None,
) -> dict:
    """List projects and optionally fetch available projects from Citeck.

    Routes through ept_profile if set, otherwise the active profile.

    Args:
        fetch: If true, query the Citeck API for all available projects and cache them.
        profile: Override the profile for this call only. Usually leave empty.
    """
    config_dir = _get_config_dir()

    try:
        resolved, creds = resolve_ept_profile(profile=profile, config_dir=config_dir)
        cache_url = creds["url"]
        cache_key = (resolved, cache_url)

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
                profile=resolved,
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
            "projects": get_projects(profile=resolved, config_dir=config_dir),
            "default_project": get_default_project(profile=resolved, config_dir=config_dir),
        }

        # Include cached fetched projects for the resolved profile+url
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
    profile: str | None = None,
) -> dict:
    """Set the default project for Citeck task-tracker operations.

    Auto-adds the project to the saved list if not already present.
    Persisted under ept_profile if set, otherwise the active profile.

    Args:
        project: Project key to set as default (e.g. "COREDEV").
        profile: Override the profile for this call only. Usually leave empty.
    """
    if not project or not project.strip():
        return {"ok": False, "error": "Project key must not be empty"}

    config_dir = _get_config_dir()

    try:
        resolved, _ = resolve_ept_profile(profile=profile, config_dir=config_dir)
        set_default_project(project, profile=resolved, config_dir=config_dir)
        return {
            "ok": True,
            "default_project": project,
            "projects": get_projects(profile=resolved, config_dir=config_dir),
        }
    except ConfigError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


_RAG_MAX_CONTENT_CHARS = 2000
_DOC_SOURCE_EXTENSIONS = (".rst", ".md", ".txt", ".adoc")


def _build_doc_url(metadata: dict) -> str | None:
    """Construct a published-docs URL from RAG metadata.

    Mirrors ecos-ai's DocumentationContentProcessor.buildDocumentationUrl:
    strips docs_root_path prefix, replaces the source extension with
    url_extension, and joins with base_doc_url. Returns None when
    base_doc_url or file_path is missing.
    """
    base = (metadata.get("base_doc_url") or "").strip()
    file_path = (metadata.get("file_path") or "").strip()
    if not base or not file_path:
        return None
    path = file_path
    root = (metadata.get("docs_root_path") or "").strip("/")
    if root:
        prefix = root + "/"
        if path.startswith(prefix):
            path = path[len(prefix):]
    ext = metadata.get("url_extension") or ""
    for src_ext in _DOC_SOURCE_EXTENSIONS:
        if path.endswith(src_ext):
            path = path[: -len(src_ext)] + ext
            break
    return base.rstrip("/") + "/" + path.lstrip("/")


def _trim_docs_hit(hit: dict) -> dict:
    """Strip noisy metadata from a RAG search result and truncate content."""
    metadata = hit.get("metadata") or {}
    content = hit.get("content") or ""
    if len(content) > _RAG_MAX_CONTENT_CHARS:
        content = content[:_RAG_MAX_CONTENT_CHARS] + "…"
    result = {
        "score": hit.get("score"),
        "file_path": metadata.get("file_path", ""),
        "file_type": metadata.get("file_type", ""),
        "source_id": hit.get("sourceId") or metadata.get("source_id", ""),
        "content": content,
    }
    url = _build_doc_url(metadata)
    if url:
        result["url"] = url
    return result


@mcp.tool
def search_docs(
    question: str,
    top_k: int = RAG_DEFAULT_TOP_K,
    threshold: float = RAG_DEFAULT_THRESHOLD,
    profile: str | None = None,
) -> dict:
    """Search Citeck ECOS platform documentation (citeck-docs) via RAG.

    Use this tool for questions about the Citeck platform itself — how-to,
    configuration, concepts, APIs. Routes through the configured docs_profile
    if set, otherwise through the active profile. If the active profile points
    to a local Citeck without a RAG index, set a docs_profile via
    `set_docs_profile` to target a server where citeck-docs is indexed.

    Args:
        question: Natural-language question about Citeck documentation.
        top_k: Max number of matching snippets to return (default: 5).
        threshold: Similarity threshold 0.0-1.0 (default: 0.4).
        profile: Override the profile for this call only. Usually leave empty.
    """
    if not question or not question.strip():
        return {"ok": False, "error": "question must not be empty."}

    config_dir = _get_config_dir()
    try:
        resolved, creds = resolve_docs_profile(profile=profile, config_dir=config_dir)
        raw_results = lib_search_docs(
            query=question,
            top_k=top_k,
            threshold=threshold,
            profile=resolved,
            config_dir=config_dir,
        )
        results = [_trim_docs_hit(hit) for hit in raw_results]
        return {
            "ok": True,
            "count": len(results),
            "profile": resolved,
            "server": creds["url"].rstrip("/"),
            "results": results,
        }
    except RagApiError as e:
        return {"ok": False, "error": str(e)}
    except AuthError as e:
        return {"ok": False, "error": str(e)}
    except ConfigError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


@mcp.tool
def set_docs_profile(profile: str) -> dict:
    """Set which credentials profile hosts the citeck-docs RAG index.

    Use this when the active profile points to a local Citeck without RAG,
    but documentation questions should be routed to a different server where
    citeck-docs is indexed. Pass an empty string to clear the setting and
    fall back to the active profile.

    Args:
        profile: Profile name (must already be configured via /citeck:citeck-auth),
                 or empty string to clear the setting.
    """
    config_dir = _get_config_dir()
    try:
        if not profile or not profile.strip():
            clear_docs_profile(config_dir)
            return {"ok": True, "docs_profile": None, "cleared": True}
        lib_set_docs_profile(profile, config_dir)
        creds = get_credentials(profile, config_dir)
        return {"ok": True, "docs_profile": profile, "server": creds["url"].rstrip("/")}
    except ConfigError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


@mcp.tool
def set_ept_profile(profile: str) -> dict:
    """Set which credentials profile handles task-tracker (ept) tools.

    Affects search_issues, create_issue, update_issue, list_projects,
    set_project_default, query_sprints/components/tags/releases, query_comments,
    and download_attachment. Use this when the task tracker lives on a different
    environment than the active profile (e.g. production tracker, local for
    everything else). Pass an empty string to clear the setting and fall back
    to the active profile.

    Args:
        profile: Profile name (must already be configured via /citeck:citeck-auth),
                 or empty string to clear the setting.
    """
    config_dir = _get_config_dir()
    try:
        if not profile or not profile.strip():
            clear_ept_profile(config_dir)
            return {"ok": True, "ept_profile": None, "cleared": True}
        lib_set_ept_profile(profile, config_dir)
        creds = get_credentials(profile, config_dir)
        return {"ok": True, "ept_profile": profile, "server": creds["url"].rstrip("/")}
    except ConfigError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


@mcp.tool
def set_records_profile(profile: str) -> dict:
    """Set which credentials profile handles plain records_query / records_mutate.

    Use this when records queries should run against a different environment
    than the task tracker (e.g. tracker on production, records on local).
    Pass an empty string to clear the setting and fall back to the active
    profile.

    Args:
        profile: Profile name (must already be configured via /citeck:citeck-auth),
                 or empty string to clear the setting.
    """
    config_dir = _get_config_dir()
    try:
        if not profile or not profile.strip():
            clear_records_profile(config_dir)
            return {"ok": True, "records_profile": None, "cleared": True}
        lib_set_records_profile(profile, config_dir)
        creds = get_credentials(profile, config_dir)
        return {"ok": True, "records_profile": profile, "server": creds["url"].rstrip("/")}
    except ConfigError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


@mcp.tool
def list_profiles() -> dict:
    """List all configured Citeck profiles with non-sensitive metadata.

    Returns the active profile, the specialized profiles (docs/ept/records,
    if set), and a list of profile entries — each with name, url, auth_method,
    is_active, is_docs, is_ept, is_records. Passwords and client secrets are
    never returned.

    Use this to see which environments are configured before calling
    set_active_profile (e.g. user says "switch to production" — call this
    first to find the matching profile by name or url).
    """
    config_dir = _get_config_dir()
    try:
        active = get_active_profile(config_dir)
        docs = lib_get_docs_profile(config_dir)
        ept = lib_get_ept_profile(config_dir)
        records = lib_get_records_profile(config_dir)
        names = get_profiles(config_dir)
        profiles = []
        for name in names:
            creds = get_credentials(name, config_dir) or {}
            # Explicit whitelist — `creds` also contains password/client_secret.
            profiles.append({
                "name": name,
                "url": creds.get("url"),
                "auth_method": creds.get("auth_method"),
                "is_active": name == active,
                "is_docs": name == docs,
                "is_ept": name == ept,
                "is_records": name == records,
            })
        return {
            "ok": True,
            "active": active,
            "docs_profile": docs,
            "ept_profile": ept,
            "records_profile": records,
            "profiles": profiles,
        }
    except ConfigError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


@mcp.tool
def set_active_profile(profile: str) -> dict:
    """Switch the active Citeck profile (used by all records and issue tools).

    The profile must already be configured via /citeck:citeck-auth — this only
    switches between existing profiles, it cannot create new ones. Call
    list_profiles first to see what's configured.

    Args:
        profile: Profile name to activate (e.g. "prod", "local").
    """
    config_dir = _get_config_dir()
    if not profile or not profile.strip():
        return {"ok": False, "error": "Profile name is required"}
    try:
        lib_set_active_profile(profile, config_dir)
        creds = get_credentials(profile, config_dir) or {}
        return {
            "ok": True,
            "active_profile": profile,
            "server": creds.get("url"),
            "auth_method": creds.get("auth_method"),
        }
    except ConfigError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


_ISSUE_SOURCE_ID = "emodel/ept-issue"
_RELEASE_SOURCE_ID = "emodel/ecos-release-type"


def _release_refs(values: list[str]) -> list[str]:
    """Prefix bare release ids with the release source ref."""
    refs = []
    for v in values:
        if not v.startswith(f"{_RELEASE_SOURCE_ID}@"):
            v = f"{_RELEASE_SOURCE_ID}@{v}"
        refs.append(v)
    return refs


def _issue_refs(values: list[str]) -> list[str]:
    """Prefix bare issue keys with the issue source ref (e.g. 'COREDEV-1' -> 'emodel/ept-issue@COREDEV-1')."""
    refs = []
    for v in values:
        if not v.startswith(f"{_ISSUE_SOURCE_ID}@"):
            v = f"{_ISSUE_SOURCE_ID}@{v}"
        refs.append(v)
    return refs


def _issue_ref(value: str) -> str:
    """Prefix a bare issue key with the issue source ref. For single-valued epic link etc."""
    if value.startswith(f"{_ISSUE_SOURCE_ID}@"):
        return value
    return f"{_ISSUE_SOURCE_ID}@{value}"


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

# Human-readable display labels for previews (short type name -> label with emoji).
_ISSUE_TYPE_DISPLAY = {
    "ept-issue-task": "✅ Task",
    "ept-issue-story": "📗 Story",
    "ept-issue-bug": "🐞 Bug",
    "ept-issue-epic": "🏔️ Epic",
}

_PRIORITY_DISPLAY = {
    "100_critical": "🔴 Critical",
    "200_high": "🟠 High",
    "300_medium": "🟡 Medium",
    "400_low": "🟢 Low",
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
    profile: str | None = None,
) -> dict:
    """Search issues in Citeck Project Tracker.

    Routes through ept_profile if set, otherwise the active profile.

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
        profile: Override the profile for this call only. Usually leave empty.
    """
    config_dir = _get_config_dir()

    try:
        resolved, creds = resolve_ept_profile(profile=profile, config_dir=config_dir)

        # Build query
        if raw_query is not None:
            query = raw_query
        else:
            # Resolve assignee "me" only when using structured filters
            ok, resolved_assignee = _resolve_assignee(assignee, resolved, config_dir)
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
        proj = project or get_default_project(profile=resolved, config_dir=config_dir)
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
            profile=resolved,
            config_dir=config_dir,
        )

        records = response.get("records", [])
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
    fix_in_version: list[str] | None = None,
    affected_versions: list[str] | None = None,
    epic: str | None = None,
    links_relates: list[str] | None = None,
    links_blocker: list[str] | None = None,
    links_duplicate: list[str] | None = None,
    links_clone: list[str] | None = None,
    links_problem: list[str] | None = None,
) -> dict:
    """Build a mutation record for issue creation."""
    attributes = {
        "_type?str": _ISSUE_TYPE_SHORT_NAMES[issue_type],
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

    if fix_in_version:
        attributes["fixInVersion?assoc"] = _release_refs(fix_in_version)

    if affected_versions:
        attributes["affectedVersions?assoc"] = _release_refs(affected_versions)

    if epic:
        attributes["epicLink?str"] = _issue_ref(epic)

    if links_relates:
        attributes["issue-links:relates?assoc"] = _issue_refs(links_relates)
    if links_blocker:
        attributes["issue-links:blocker?assoc"] = _issue_refs(links_blocker)
    if links_duplicate:
        attributes["issue-links:duplicate?assoc"] = _issue_refs(links_duplicate)
    if links_clone:
        attributes["issue-links:clone?assoc"] = _issue_refs(links_clone)
    if links_problem:
        attributes["issue-links:problem?assoc"] = _issue_refs(links_problem)

    return {
        "id": f"{_ISSUE_SOURCE_ID}@",
        "attributes": attributes,
    }


def _prepare_create_record(
    *,
    type: str,
    summary: str,
    project: str | None,
    description: str,
    priority: str,
    assignee: str | None,
    sprint: str | None,
    components: list[str] | None,
    tags: list[str] | None,
    fix_in_version: list[str] | None,
    affected_versions: list[str] | None,
    epic: str | None,
    links_relates: list[str] | None,
    links_blocker: list[str] | None,
    links_duplicate: list[str] | None,
    links_clone: list[str] | None,
    links_problem: list[str] | None,
    profile: str | None,
    config_dir: str | None,
) -> tuple[dict, str, str]:
    """Resolve inputs and build a create-issue mutation record.

    Returns (record, resolved_profile, server_url). Raises ValueError on
    validation errors. Shared by create_issue (mutates) and preview_issue
    (read-only) so the two never drift.
    """
    resolved, creds = resolve_ept_profile(profile=profile, config_dir=config_dir)

    if not summary:
        raise ValueError("Summary is required.")
    if type not in _ISSUE_TYPE_SHORT_NAMES:
        valid = ", ".join(_ISSUE_TYPE_SHORT_NAMES.keys())
        raise ValueError(f"Unknown issue type '{type}'. Valid types: {valid}.")

    proj_key = project or get_default_project(profile=resolved, config_dir=config_dir)
    if not proj_key:
        raise ValueError(
            "Project is required (no default project set). "
            "Use set_project_default to set one."
        )

    ok, resolved_assignee = _resolve_assignee(assignee, resolved, config_dir)
    if not ok:
        raise ValueError(resolved_assignee)

    try:
        reporter = get_username(profile=resolved, config_dir=config_dir)
    except Exception:
        reporter = None

    project_ref, workspace_key = _resolve_project_info(proj_key, profile=resolved, config_dir=config_dir)

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
        fix_in_version=fix_in_version,
        affected_versions=affected_versions,
        epic=epic,
        links_relates=links_relates,
        links_blocker=links_blocker,
        links_duplicate=links_duplicate,
        links_clone=links_clone,
        links_problem=links_problem,
    )
    return record, resolved, creds["url"].rstrip("/")


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
    fix_in_version: list[str] | None = None,
    affected_versions: list[str] | None = None,
    epic: str | None = None,
    links_relates: list[str] | None = None,
    links_blocker: list[str] | None = None,
    links_duplicate: list[str] | None = None,
    links_clone: list[str] | None = None,
    links_problem: list[str] | None = None,
    profile: str | None = None,
) -> dict:
    """Create an issue in Citeck Project Tracker. This actually creates the issue.

    Routes through ept_profile if set, otherwise the active profile.

    IMPORTANT: Call preview_issue first, show the FULL preview to the user, and get
    explicit confirmation before calling this tool. preview_issue is read-only and
    renders a human-readable preview without creating anything.

    Args:
        type: Issue type: task, story, bug, epic.
        summary: Issue summary/title in English, imperative mood (required).
        project: Project key (e.g. "COREDEV"). Uses default project if not set.
        description: Issue description in Russian, HTML format (Lexical editor). Use tags: <p>, <h2>, <h3>, <ul>/<li>, <ol>/<li>, <code>, <b>, <i>.
        priority: Priority (default: "300_medium"). Options: 100_critical, 200_high, 300_medium, 400_low.
        assignee: Assignee username. Use "me" to auto-resolve to current user.
        sprint: Sprint reference (UUID or full ref).
        components: List of component references.
        tags: List of tag references.
        fix_in_version: Target releases — list of release references (UUID or full "emodel/ecos-release-type@" ref). Use query_releases to find them.
        affected_versions: Affected releases — list of release references (UUID or full "emodel/ecos-release-type@" ref). Use query_releases to find them.
        epic: Epic link — single issue reference (PROJECT-N key or full "emodel/ept-issue@" ref) pointing to an epic issue.
        links_relates: Issue links of type "relates to" — list of issue references (PROJECT-N keys or full "emodel/ept-issue@" refs).
        links_blocker: Issue links of type "is blocked by" — list of issue references.
        links_duplicate: Issue links of type "duplicates" — list of issue references.
        links_clone: Issue links of type "is cloned from" — list of issue references.
        links_problem: Issue links of type "is caused by" / problem — list of issue references.
        profile: Override the profile for this call only. Usually leave empty.

    Reporter is auto-set to the current user.
    """
    config_dir = _get_config_dir()

    try:
        record, resolved, server_url = _prepare_create_record(
            type=type,
            summary=summary,
            project=project,
            description=description,
            priority=priority,
            assignee=assignee,
            sprint=sprint,
            components=components,
            tags=tags,
            fix_in_version=fix_in_version,
            affected_versions=affected_versions,
            epic=epic,
            links_relates=links_relates,
            links_blocker=links_blocker,
            links_duplicate=links_duplicate,
            links_clone=links_clone,
            links_problem=links_problem,
            profile=profile,
            config_dir=config_dir,
        )

        # Actually create
        result = lib_records_mutate(
            records=[record],
            version=1,
            profile=resolved,
            config_dir=config_dir,
        )

        result_records = result.get("records", [])
        if result_records:
            created_id = result_records[0].get("id", "unknown")
            response = {
                "ok": True,
                "id": created_id,
                "profile": resolved,
                "server": server_url,
            }
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
    fix_in_version: list[str] | None = None,
    affected_versions: list[str] | None = None,
    epic: str | None = None,
    links_relates: list[str] | None = None,
    links_blocker: list[str] | None = None,
    links_duplicate: list[str] | None = None,
    links_clone: list[str] | None = None,
    links_problem: list[str] | None = None,
) -> dict:
    """Build a mutation record for issue update."""
    attributes: dict = {}

    if status is not None:
        attributes["_status?str"] = status
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
    if fix_in_version is not None:
        attributes["fixInVersion?assoc"] = _release_refs(fix_in_version)
    if affected_versions is not None:
        attributes["affectedVersions?assoc"] = _release_refs(affected_versions)
    if epic is not None:
        attributes["epicLink?str"] = _issue_ref(epic) if epic else ""
    if links_relates is not None:
        attributes["issue-links:relates?assoc"] = _issue_refs(links_relates)
    if links_blocker is not None:
        attributes["issue-links:blocker?assoc"] = _issue_refs(links_blocker)
    if links_duplicate is not None:
        attributes["issue-links:duplicate?assoc"] = _issue_refs(links_duplicate)
    if links_clone is not None:
        attributes["issue-links:clone?assoc"] = _issue_refs(links_clone)
    if links_problem is not None:
        attributes["issue-links:problem?assoc"] = _issue_refs(links_problem)

    if not attributes:
        raise ValueError(
            "No attributes to update. Specify at least one of: "
            "status, assignee, priority, summary, description, "
            "fix_in_version, affected_versions, epic, "
            "links_relates, links_blocker, links_duplicate, "
            "links_clone, links_problem."
        )

    attributes["_workspace?str"] = _resolve_workspace_from_issue(issue_id)

    return {
        "id": _resolve_issue_ref(issue_id),
        "attributes": attributes,
    }


def _prepare_update_record(
    *,
    issue: str,
    status: str | None,
    assignee: str | None,
    priority: str | None,
    summary: str | None,
    description: str | None,
    fix_in_version: list[str] | None,
    affected_versions: list[str] | None,
    epic: str | None,
    links_relates: list[str] | None,
    links_blocker: list[str] | None,
    links_duplicate: list[str] | None,
    links_clone: list[str] | None,
    links_problem: list[str] | None,
    profile: str | None,
    config_dir: str | None,
) -> tuple[dict, str, str]:
    """Resolve inputs and build an update-issue mutation record.

    Returns (record, resolved_profile, server_url). Raises ValueError on
    validation errors. Shared by update_issue (mutates) and preview_issue
    (read-only).
    """
    resolved, creds = resolve_ept_profile(profile=profile, config_dir=config_dir)

    ok, resolved_assignee = _resolve_assignee(assignee, resolved, config_dir)
    if not ok:
        raise ValueError(resolved_assignee)

    record = _build_update_record(
        issue_id=issue,
        status=status,
        assignee=resolved_assignee,
        priority=priority,
        summary=summary,
        description=description,
        fix_in_version=fix_in_version,
        affected_versions=affected_versions,
        epic=epic,
        links_relates=links_relates,
        links_blocker=links_blocker,
        links_duplicate=links_duplicate,
        links_clone=links_clone,
        links_problem=links_problem,
    )
    return record, resolved, creds["url"].rstrip("/")


@mcp.tool
def update_issue(
    issue: str,
    status: str | None = None,
    assignee: str | None = None,
    priority: str | None = None,
    summary: str | None = None,
    description: str | None = None,
    fix_in_version: list[str] | None = None,
    affected_versions: list[str] | None = None,
    epic: str | None = None,
    links_relates: list[str] | None = None,
    links_blocker: list[str] | None = None,
    links_duplicate: list[str] | None = None,
    links_clone: list[str] | None = None,
    links_problem: list[str] | None = None,
    profile: str | None = None,
) -> dict:
    """Update an issue in Citeck Project Tracker. This actually updates the issue.

    Routes through ept_profile if set, otherwise the active profile.

    IMPORTANT: Call preview_issue (with the same `issue`) first, show the FULL preview
    to the user, and get explicit confirmation before calling this tool. preview_issue
    is read-only and renders a human-readable preview without changing anything.

    Args:
        issue: Issue ID (e.g. "COREDEV-42") or full record ref with PROJECT-NUMBER local ID
               (e.g. "emodel/ept-issue@COREDEV-42"). UUID-based refs are not supported.
        status: New status (e.g. "in-progress", "done", "to-do").
        assignee: New assignee username. Use "me" to auto-resolve to current user.
        priority: New priority (e.g. "100_critical", "200_high", "300_medium", "400_low").
        summary: New summary/title in English.
        description: New description in Russian, HTML format (Lexical editor). Use tags: <p>, <h2>, <h3>, <ul>/<li>, <ol>/<li>, <code>, <b>, <i>.
        fix_in_version: Target releases — list of release references (UUID or full "emodel/ecos-release-type@" ref). Replaces the current value. Use query_releases to find them.
        affected_versions: Affected releases — list of release references (UUID or full "emodel/ecos-release-type@" ref). Replaces the current value. Use query_releases to find them.
        epic: Epic link — single issue reference (PROJECT-N key or full "emodel/ept-issue@" ref). Pass empty string to clear.
        links_relates: Issue links of type "relates to" — list of issue references. Replaces the current value (empty list clears).
        links_blocker: Issue links of type "is blocked by" — list of issue references. Replaces the current value.
        links_duplicate: Issue links of type "duplicates" — list of issue references. Replaces the current value.
        links_clone: Issue links of type "is cloned from" — list of issue references. Replaces the current value.
        links_problem: Issue links of type "is caused by" / problem — list of issue references. Replaces the current value.
        profile: Override the profile for this call only. Usually leave empty.
    """
    config_dir = _get_config_dir()

    try:
        record, resolved, server_url = _prepare_update_record(
            issue=issue,
            status=status,
            assignee=assignee,
            priority=priority,
            summary=summary,
            description=description,
            fix_in_version=fix_in_version,
            affected_versions=affected_versions,
            epic=epic,
            links_relates=links_relates,
            links_blocker=links_blocker,
            links_duplicate=links_duplicate,
            links_clone=links_clone,
            links_problem=links_problem,
            profile=profile,
            config_dir=config_dir,
        )

        # Actually update
        result = lib_records_mutate(
            records=[record],
            version=1,
            profile=resolved,
            config_dir=config_dir,
        )

        result_records = result.get("records", [])
        if result_records:
            updated_id = result_records[0].get("id", "unknown")
            return {
                "ok": True,
                "id": updated_id,
                "profile": resolved,
                "server": server_url,
                "link": f"{server_url}/v2/dashboard?recordRef={updated_id}",
            }
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
    profile: str | None = None,
) -> dict:
    """Generic metadata query for sprints, components, tags, releases."""
    config_dir = _get_config_dir()
    cfg = _METADATA_CONFIGS[entity_type]

    try:
        resolved, _ = resolve_ept_profile(profile=profile, config_dir=config_dir)

        proj = project or get_default_project(profile=resolved, config_dir=config_dir)
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
            profile=resolved,
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
    profile: str | None = None,
) -> dict:
    """Query sprints in Citeck Project Tracker.

    Routes through ept_profile if set, otherwise the active profile.

    Args:
        project: Project/workspace key (e.g. "COREDEV"). Uses default project if not set.
        status: Filter by status (e.g. "new", "in-progress", "completed").
        limit: Max results (default: 20).
        ascending: Sort ascending by creation date (default: false).
        profile: Override the profile for this call only. Usually leave empty.
    """
    return _query_metadata("sprints", project=project, status=status, limit=limit, ascending=ascending, profile=profile)


@mcp.tool
def query_components(
    project: str | None = None,
    limit: int = 50,
    ascending: bool = False,
    profile: str | None = None,
) -> dict:
    """Query components in Citeck Project Tracker.

    Routes through ept_profile if set, otherwise the active profile.

    Args:
        project: Project/workspace key (e.g. "COREDEV"). Uses default project if not set.
        limit: Max results (default: 50).
        ascending: Sort ascending by creation date (default: false).
        profile: Override the profile for this call only. Usually leave empty.
    """
    return _query_metadata("components", project=project, limit=limit, ascending=ascending, profile=profile)


@mcp.tool
def query_tags(
    project: str | None = None,
    limit: int = 50,
    ascending: bool = False,
    profile: str | None = None,
) -> dict:
    """Query tags in Citeck Project Tracker.

    Routes through ept_profile if set, otherwise the active profile.

    Args:
        project: Project/workspace key (e.g. "COREDEV"). Uses default project if not set.
        limit: Max results (default: 50).
        ascending: Sort ascending by creation date (default: false).
        profile: Override the profile for this call only. Usually leave empty.
    """
    return _query_metadata("tags", project=project, limit=limit, ascending=ascending, profile=profile)


@mcp.tool
def query_releases(
    project: str | None = None,
    status: str | None = None,
    limit: int = 20,
    ascending: bool = False,
    profile: str | None = None,
) -> dict:
    """Query releases in Citeck Project Tracker.

    Routes through ept_profile if set, otherwise the active profile.

    Args:
        project: Project/workspace key (e.g. "COREDEV"). Uses default project if not set.
        status: Filter by status (e.g. "new", "in-progress", "completed").
        limit: Max results (default: 20).
        ascending: Sort ascending by creation date (default: false).
        profile: Override the profile for this call only. Usually leave empty.
    """
    return _query_metadata("releases", project=project, status=status, limit=limit, ascending=ascending, profile=profile)


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


# --- Preview rendering (HTML -> markdown, ref resolution, human-readable previews) ---


class _MarkdownConverter(HTMLParser):
    """Convert the limited Lexical HTML tag set into terminal-friendly markdown.

    Handles: <p>, <h1..h6>, <ul>/<ol>/<li> (nested), <b>/<strong>, <i>/<em>,
    <code>, <a href>, <br>, <img src>, <blockquote>. Unknown tags are ignored
    but their text is kept.
    """

    _BLOCK_START = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "div"}

    def __init__(self):
        super().__init__()
        self.blocks: list[str] = []
        self._buf: list[str] = []
        self._list_stack: list[list] = []  # each entry: [kind, counter]
        self._href: str = ""

    def _flush(self, prefix: str = "") -> None:
        text = re.sub(r"[ \t]+", " ", "".join(self._buf)).strip()
        self._buf = []
        if text:
            self.blocks.append(prefix + text)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in self._BLOCK_START:
            self._flush()
        if tag == "ul":
            self._list_stack.append(["ul", 0])
        elif tag == "ol":
            self._list_stack.append(["ol", 0])
        elif tag in ("b", "strong"):
            self._buf.append("**")
        elif tag in ("i", "em"):
            self._buf.append("*")
        elif tag == "code":
            self._buf.append("`")
        elif tag == "a":
            self._href = a.get("href", "")
            self._buf.append("[")
        elif tag == "br":
            self._flush()
        elif tag == "img":
            src = a.get("src", "")
            if src:
                self._buf.append(f"![image]({src})")

    def handle_endtag(self, tag):
        if tag in ("p", "div"):
            self._flush()
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._flush("#" * int(tag[1]) + " ")
        elif tag == "blockquote":
            self._flush("> ")
        elif tag == "li":
            if self._list_stack:
                kind = self._list_stack[-1]
                indent = "  " * (len(self._list_stack) - 1)
                if kind[0] == "ol":
                    kind[1] += 1
                    self._flush(f"{indent}{kind[1]}. ")
                else:
                    self._flush(f"{indent}- ")
            else:
                self._flush("- ")
        elif tag in ("ul", "ol"):
            if self._list_stack:
                self._list_stack.pop()
        elif tag in ("b", "strong"):
            self._buf.append("**")
        elif tag in ("i", "em"):
            self._buf.append("*")
        elif tag == "code":
            self._buf.append("`")
        elif tag == "a":
            self._buf.append(f"]({self._href})" if self._href else "]")
            self._href = ""

    def handle_data(self, data):
        self._buf.append(data)

    def get_markdown(self) -> str:
        self._flush()
        return "\n".join(self.blocks).strip()


def _html_to_markdown(html: str | None) -> str:
    """Render Lexical-format HTML as readable markdown for the terminal."""
    if not html:
        return ""
    conv = _MarkdownConverter()
    conv.feed(html)
    return conv.get_markdown()


def _indent(text: str, prefix: str = "  ") -> str:
    """Indent every non-empty line of text with prefix."""
    return "\n".join(prefix + line if line.strip() else line for line in text.split("\n"))


# Attribute keys whose values are record refs (single-valued / list-valued).
_PREVIEW_REF_KEYS_SINGLE = (
    "link-project:project?str", "implementer?str", "reporter?str", "epicLink?str",
)
_PREVIEW_REF_KEYS_LIST = (
    "sprint?assoc", "components?assoc", "tags?assoc",
    "fixInVersion?assoc", "affectedVersions?assoc",
    "issue-links:relates?assoc", "issue-links:blocker?assoc",
    "issue-links:duplicate?assoc", "issue-links:clone?assoc",
    "issue-links:problem?assoc",
)


def _collect_refs(attrs: dict) -> list[str]:
    """Gather every record ref present in a mutation record's attributes."""
    refs: list[str] = []
    for key in _PREVIEW_REF_KEYS_SINGLE:
        val = attrs.get(key)
        if val:
            refs.append(val)
    for key in _PREVIEW_REF_KEYS_LIST:
        val = attrs.get(key)
        if isinstance(val, list):
            refs.extend(r for r in val if r)
        elif val:
            refs.append(val)
    return refs


def _resolve_ref_labels(refs, profile, config_dir) -> dict:
    """Batch-resolve record refs to their display names in one query.

    Returns a {ref: display_name} map. Refs that fail to resolve are omitted,
    so callers can flag them as missing.
    """
    unique = [r for r in dict.fromkeys(refs) if r]
    if not unique:
        return {}
    try:
        result = lib_records_load(
            record_ids=unique,
            attributes={"disp": "?disp"},
            profile=profile,
            config_dir=config_dir,
        )
    except Exception:
        return {}
    labels = {}
    for rec in result.get("records", []):
        rid = rec.get("id")
        disp = (rec.get("attributes") or {}).get("disp")
        if rid and disp:
            labels[rid] = disp
    return labels


def _ref_link(ref: str, labels: dict, server_url: str) -> str:
    """Render a record ref as a markdown link to its dashboard, or flag if unresolved."""
    label = labels.get(ref)
    if not label:
        return f"⚠️ {ref} (не найдено)"
    quoted = urllib.parse.quote(ref, safe="@/:")
    return f"[{label}]({server_url}/v2/dashboard?recordRef={quoted})"


# Ordered preview layout: (attribute key, human label, render kind).
_PREVIEW_FIELD_ORDER = (
    ("_type?str", "Тип", "type"),
    ("link-project:project?str", "Проект", "reflink"),
    ("_workspace?str", "Воркспейс", "plain"),
    ("_state?str", "Статус", "plain"),
    ("_status?str", "Статус", "plain"),
    ("summary?str", "Заголовок", "plain"),
    ("priority?str", "Приоритет", "priority"),
    ("implementer?str", "Исполнитель", "reflink"),
    ("reporter?str", "Автор", "reflink"),
    ("sprint?assoc", "Спринт", "reflinks"),
    ("components?assoc", "Компоненты", "reflinks"),
    ("tags?assoc", "Теги", "reflinks"),
    ("fixInVersion?assoc", "Целевые релизы", "reflinks"),
    ("affectedVersions?assoc", "Затронутые релизы", "reflinks"),
    ("epicLink?str", "Эпик", "reflink"),
    ("issue-links:relates?assoc", "Связи · relates to", "reflinks"),
    ("issue-links:blocker?assoc", "Связи · blocked by", "reflinks"),
    ("issue-links:duplicate?assoc", "Связи · duplicates", "reflinks"),
    ("issue-links:clone?assoc", "Связи · cloned from", "reflinks"),
    ("issue-links:problem?assoc", "Связи · caused by", "reflinks"),
)


def _render_preview_value(val, kind: str, labels: dict, server_url: str):
    """Render one attribute value for the preview. Returns None to skip the field."""
    if kind == "type":
        return _ISSUE_TYPE_DISPLAY.get(val, val)
    if kind == "priority":
        return _PRIORITY_DISPLAY.get(val, val)
    if kind == "plain":
        return val or None
    if kind == "reflink":
        if not val:
            return "— (очистить)"
        return _ref_link(val, labels, server_url)
    if kind == "reflinks":
        items = val if isinstance(val, list) else ([val] if val else [])
        items = [r for r in items if r]
        if not items:
            return "— (очистить)"
        return ", ".join(_ref_link(r, labels, server_url) for r in items)
    return str(val)


def _format_record_preview(record: dict, labels: dict, server_url: str, profile: str, mode: str) -> str:
    """Build a human-readable markdown preview from a mutation record."""
    attrs = record.get("attributes", {})
    if mode == "create":
        head = "Создание задачи"
    else:
        local = record.get("id", "").split("@")[-1]
        head = f"Обновление {local}"

    lines = [f"📋 Превью — {head}", f"_профиль: {profile} · {server_url}_", ""]
    for key, label, kind in _PREVIEW_FIELD_ORDER:
        if key not in attrs:
            continue
        rendered = _render_preview_value(attrs[key], kind, labels, server_url)
        if rendered is None:
            continue
        lines.append(f"**{label}:** {rendered}")

    if "description?str" in attrs:
        md = _html_to_markdown(attrs["description?str"])
        lines.append("")
        lines.append("**Описание:**")
        lines.append(_indent(md) if md else "  _(пусто)_")

    return "\n".join(lines)


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
    profile: str | None = None,
) -> dict:
    """Fetch comments for a Citeck ECOS record.

    Routes through ept_profile if set, otherwise the active profile.

    Comments are sorted newest first. The 'text' field is plain text
    (HTML stripped); 'textHtml' preserves the original HTML.
    Images from comments are automatically downloaded to ~/.citeck/downloads/
    and returned as 'images' list with local file paths. Use the Read tool
    to view the downloaded images.

    Args:
        record_ref: Full record reference (e.g. "emodel/ept-issue@COREDEV-3703").
        limit: Max comments to return (default: 50).
        skip_count: Number of comments to skip for pagination (default: 0).
        profile: Override the profile for this call only. Usually leave empty.
    """
    config_dir = _get_config_dir()

    if not record_ref or not record_ref.strip():
        return {"ok": False, "error": "record_ref must not be empty."}

    try:
        resolved, creds = resolve_ept_profile(profile=profile, config_dir=config_dir)

        response = lib_records_query(
            source_id=_COMMENT_SOURCE_ID,
            query={"t": "eq", "a": "record", "v": record_ref},
            attributes=_COMMENT_ATTRIBUTES,
            language="predicate",
            page={"skipCount": skip_count, "maxItems": limit},
            sort_by=[{"attribute": "_created", "ascending": False}],
            profile=resolved,
            config_dir=config_dir,
        )

        records = response.get("records", [])
        base_url = creds["url"].rstrip("/")
        comments = _format_comments(records, base_url=base_url)

        # Auto-download images from comments and replace URLs with local paths
        try:
            auth_header = get_auth_header(profile=resolved, config_dir=config_dir)
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

    except ConfigError as e:
        return {"ok": False, "error": str(e)}
    except RecordsApiError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


def _build_comment_record(issue_id: str, text: str) -> dict:
    """Build a mutation record for adding a comment to an issue."""
    return {
        "id": f"{_COMMENT_SOURCE_ID}@",
        "attributes": {
            "text?str": text,
            "record?str": _issue_ref(issue_id),
            "_workspace?str": _resolve_workspace_from_issue(issue_id),
        },
    }


def _prepare_comment_record(
    issue: str, text: str, profile: str | None, config_dir: str | None
) -> tuple[dict, str, str]:
    """Validate inputs and build a comment mutation record.

    Returns (record, resolved_profile, server_url). Raises ValueError on
    validation errors. Shared by add_comment (mutates) and preview_comment
    (read-only).
    """
    if not text or not text.strip():
        raise ValueError("Comment text is required.")
    resolved, creds = resolve_ept_profile(profile=profile, config_dir=config_dir)
    record = _build_comment_record(issue_id=issue, text=text)
    return record, resolved, creds["url"].rstrip("/")


@mcp.tool
def add_comment(
    issue: str,
    text: str,
    profile: str | None = None,
) -> dict:
    """Add a comment to an issue in Citeck Project Tracker. This actually posts the comment.

    Routes through ept_profile if set, otherwise the active profile.

    IMPORTANT: Call preview_comment first, show the FULL preview to the user, and get
    explicit confirmation before calling this tool. preview_comment is read-only and
    renders the comment as human-readable text without posting anything.

    Args:
        issue: Issue ID (e.g. "COREDEV-42") or full record ref with PROJECT-NUMBER local ID
               (e.g. "emodel/ept-issue@COREDEV-42"). UUID-based refs are not supported.
        text: Comment body in Russian, HTML format (Lexical editor). Use tags: <p>, <h2>, <h3>, <ul>/<li>, <ol>/<li>, <code>, <b>, <i>.
        profile: Override the profile for this call only. Usually leave empty.
    """
    config_dir = _get_config_dir()

    try:
        record, resolved, server_url = _prepare_comment_record(issue, text, profile, config_dir)

        result = lib_records_mutate(
            records=[record],
            version=1,
            profile=resolved,
            config_dir=config_dir,
        )

        result_records = result.get("records", [])
        issue_ref = _issue_ref(issue)
        response: dict = {
            "ok": True,
            "profile": resolved,
            "server": server_url,
            "issue": issue_ref,
            "link": f"{server_url}/v2/dashboard?recordRef={issue_ref}",
        }
        if result_records:
            response["id"] = result_records[0].get("id", "unknown")
        return response

    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except ConfigError as e:
        return {"ok": False, "error": str(e)}
    except RecordsApiError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


@mcp.tool(annotations={"readOnlyHint": True})
def preview_issue(
    type: str | None = None,
    issue: str | None = None,
    summary: str | None = None,
    project: str | None = None,
    description: str | None = None,
    priority: str | None = None,
    assignee: str | None = None,
    status: str | None = None,
    sprint: str | None = None,
    components: list[str] | None = None,
    tags: list[str] | None = None,
    fix_in_version: list[str] | None = None,
    affected_versions: list[str] | None = None,
    epic: str | None = None,
    links_relates: list[str] | None = None,
    links_blocker: list[str] | None = None,
    links_duplicate: list[str] | None = None,
    links_clone: list[str] | None = None,
    links_problem: list[str] | None = None,
    profile: str | None = None,
) -> dict:
    """Render a human-readable preview of an issue create/update. READ-ONLY — never mutates.

    This is the tool to call BEFORE create_issue / update_issue. It is safe to run
    without confirmation (it only reads), and it returns a 'text' field with a
    terminal-friendly markdown summary: type/priority shown as labels, all references
    (project, sprint, components, tags, releases, epic, assignee) resolved to clickable
    object links, and the description rendered from Lexical HTML into readable markdown.
    Show that 'text' to the user verbatim, then call the real tool after confirmation.

    Mode is chosen automatically:
    - If 'issue' is given → preview an UPDATE (same args as update_issue; only the
      fields you pass are shown).
    - Otherwise → preview a CREATE (requires 'type'; same args as create_issue).

    Args mirror create_issue / update_issue. Returns {ok, preview, profile, server,
    text, record}. 'text' is the human-readable preview; 'record' is the raw payload.
    """
    config_dir = _get_config_dir()

    try:
        if issue:
            record, resolved, server_url = _prepare_update_record(
                issue=issue,
                status=status,
                assignee=assignee,
                priority=priority,
                summary=summary,
                description=description,
                fix_in_version=fix_in_version,
                affected_versions=affected_versions,
                epic=epic,
                links_relates=links_relates,
                links_blocker=links_blocker,
                links_duplicate=links_duplicate,
                links_clone=links_clone,
                links_problem=links_problem,
                profile=profile,
                config_dir=config_dir,
            )
            mode = "update"
        else:
            if type is None:
                return {
                    "ok": False,
                    "error": "For a create preview, 'type' is required (task/story/bug/epic). "
                             "For an update preview, pass 'issue'.",
                }
            record, resolved, server_url = _prepare_create_record(
                type=type,
                summary=summary or "",
                project=project,
                description=description or "",
                priority=priority or "300_medium",
                assignee=assignee,
                sprint=sprint,
                components=components,
                tags=tags,
                fix_in_version=fix_in_version,
                affected_versions=affected_versions,
                epic=epic,
                links_relates=links_relates,
                links_blocker=links_blocker,
                links_duplicate=links_duplicate,
                links_clone=links_clone,
                links_problem=links_problem,
                profile=profile,
                config_dir=config_dir,
            )
            mode = "create"

        labels = _resolve_ref_labels(_collect_refs(record["attributes"]), resolved, config_dir)
        text = _format_record_preview(record, labels, server_url, resolved, mode)
        return {
            "ok": True,
            "preview": True,
            "profile": resolved,
            "server": server_url,
            "text": text,
            "record": record,
        }

    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except ConfigError as e:
        return {"ok": False, "error": str(e)}
    except RecordsApiError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}


@mcp.tool(annotations={"readOnlyHint": True})
def preview_comment(
    issue: str,
    text: str,
    profile: str | None = None,
) -> dict:
    """Render a human-readable preview of a comment. READ-ONLY — never posts.

    Call this BEFORE add_comment. Safe to run without confirmation. Returns a 'text'
    field with the comment rendered from Lexical HTML into readable markdown. Show it
    to the user, then call add_comment after confirmation.

    Args:
        issue: Issue ID (e.g. "COREDEV-42") or full record ref with PROJECT-NUMBER local ID.
        text: Comment body in Russian, HTML format (Lexical editor).
        profile: Override the profile for this call only. Usually leave empty.

    Returns {ok, preview, profile, server, issue, text, record}.
    """
    config_dir = _get_config_dir()

    try:
        record, resolved, server_url = _prepare_comment_record(issue, text, profile, config_dir)
        issue_ref = _issue_ref(issue)
        md = _html_to_markdown(text)
        body = _indent(md) if md else "  _(пусто)_"
        preview_text = (
            f"📋 Превью — комментарий к {issue}\n"
            f"_профиль: {resolved} · {server_url}_\n\n"
            f"{body}"
        )
        return {
            "ok": True,
            "preview": True,
            "profile": resolved,
            "server": server_url,
            "issue": issue_ref,
            "text": preview_text,
            "record": record,
        }

    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except ConfigError as e:
        return {"ok": False, "error": str(e)}
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
    profile: str | None = None,
) -> dict:
    """Download a file from Citeck via authenticated session and return its local path.

    Routes through ept_profile if set, otherwise the active profile.

    Saves the file to ~/.citeck/downloads/. Use the Read tool with the returned
    path to view the file contents. Supports images, PDFs, and other binary files.

    Args:
        url: Attachment URL — absolute (https://...) or relative (/gateway/...).
             Relative URLs are resolved against the configured Citeck base URL.
        profile: Override the profile for this call only. Usually leave empty.
    """
    config_dir = _get_config_dir()

    if not url or not url.strip():
        return {"ok": False, "error": "url must not be empty."}

    try:
        resolved, creds = resolve_ept_profile(profile=profile, config_dir=config_dir)
        base_url = creds["url"].rstrip("/")
        auth_header = get_auth_header(profile=resolved, config_dir=config_dir)
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
