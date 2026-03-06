"""Shared HTTP client for Citeck ECOS Records API.

Wraps /gateway/api/records/{query,mutate} endpoints with
unified error handling and authentication via auth module.
"""
import json
import urllib.request
import urllib.error

from . import auth, config

QUERY_PATH = "/gateway/api/records/query"
MUTATE_PATH = "/gateway/api/records/mutate"
DEFAULT_TIMEOUT = 30


class RecordsApiError(Exception):
    """Base error for Records API failures."""

    def __init__(self, message, status_code=None, response_body=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class AuthenticationError(RecordsApiError):
    """Raised on 401/403 responses."""


class ServerError(RecordsApiError):
    """Raised on 5xx responses."""


class RecordsConnectionError(RecordsApiError):
    """Raised when the server is unreachable."""


def _get_base_url(profile=None, config_dir=None):
    """Get base URL from credentials profile."""
    creds = config.get_credentials(profile, config_dir)
    if creds is None:
        resolved = profile or config.get_active_profile(config_dir)
        raise RecordsApiError(
            f"No credentials found for profile '{resolved}'. "
            "Run 'citeck:citeck-auth' to configure."
        )
    return creds["url"].rstrip("/")


def request(path, body, profile=None, config_dir=None, timeout=DEFAULT_TIMEOUT):
    """Send a POST request to a Records API endpoint.

    Returns parsed JSON response.
    Raises typed errors for different failure modes.
    """
    try:
        base_url = _get_base_url(profile, config_dir)
        auth_header = auth.get_auth_header(profile, config_dir)
    except auth.AuthError as e:
        raise RecordsApiError(str(e)) from e
    except config.ConfigError as e:
        raise RecordsApiError(str(e)) from e

    url = base_url + path
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": auth_header,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        response_body = e.read().decode("utf-8", errors="replace")
        if e.code in (401, 403):
            raise AuthenticationError(
                f"Authentication failed: HTTP {e.code} {e.reason}. "
                "Check credentials with 'citeck:citeck-auth'.",
                status_code=e.code,
                response_body=response_body,
            ) from e
        if e.code >= 500:
            raise ServerError(
                f"Server error: HTTP {e.code} {e.reason}",
                status_code=e.code,
                response_body=response_body,
            ) from e
        raise RecordsApiError(
            f"HTTP {e.code} {e.reason}",
            status_code=e.code,
            response_body=response_body,
        ) from e
    except (urllib.error.URLError, OSError) as e:
        raise RecordsConnectionError(
            f"Cannot connect to Citeck at {base_url}: {e}"
        ) from e



def records_query(source_id, query=None, attributes=None,
                  language="", page=None,
                  consistency="EVENTUAL", sort_by=None, workspaces=None,
                  version=1,
                  profile=None, config_dir=None, timeout=DEFAULT_TIMEOUT):
    """Query records from a source.

    Args:
        source_id: Records source ID (e.g., "emodel/ept-issue")
        query: Query predicate dict (optional)
        attributes: Dict of attribute aliases to attribute names
        language: Query language (default: "")
        page: Pagination dict with 'maxItems' and/or 'skipCount'
        consistency: Query consistency mode (default: "EVENTUAL")
        sort_by: List of sort dicts with 'attribute' and 'ascending' keys
        workspaces: List of workspace/project keys to filter by
        version: API version (default: 1)
        profile: Credentials profile name (optional)
        config_dir: Config directory override (optional)
        timeout: Request timeout in seconds

    Returns:
        Parsed JSON response dict
    """
    inner_query = {"sourceId": source_id}
    if query is not None:
        inner_query["query"] = query
    if language:
        inner_query["language"] = language
    inner_query["consistency"] = consistency
    if page is not None:
        inner_query["page"] = page
    if sort_by is not None:
        inner_query["sortBy"] = sort_by
    if workspaces is not None:
        inner_query["workspaces"] = workspaces

    body = {"query": inner_query, "version": version}
    if attributes is not None:
        body["attributes"] = attributes
    return request(QUERY_PATH, body, profile, config_dir, timeout)


def records_load(record_ids, attributes=None, version=1,
                 profile=None, config_dir=None, timeout=DEFAULT_TIMEOUT):
    """Load attributes for specific records by their IDs.

    Args:
        record_ids: List of record ID strings (e.g., ["emodel/project@uuid"])
        attributes: List of attribute names (e.g., ["?json"]) or dict of aliases
        version: API version (default: 1)
        profile: Credentials profile name (optional)
        config_dir: Config directory override (optional)
        timeout: Request timeout in seconds

    Returns:
        Parsed JSON response dict
    """
    body = {"records": record_ids, "version": version}
    if attributes is not None:
        body["attributes"] = attributes
    return request(QUERY_PATH, body, profile, config_dir, timeout)


def records_mutate(records, version=1, profile=None, config_dir=None, timeout=DEFAULT_TIMEOUT):
    """Mutate (create or update) records.

    Args:
        records: List of record dicts with 'id' and 'attributes'
        version: API version (default: 1)
        profile: Credentials profile name (optional)
        config_dir: Config directory override (optional)
        timeout: Request timeout in seconds

    Returns:
        Parsed JSON response dict
    """
    body = {"records": records, "version": version}
    return request(MUTATE_PATH, body, profile, config_dir, timeout)


