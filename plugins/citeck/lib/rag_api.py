"""Shared HTTP client for Citeck RAG documentation search.

Wraps /gateway/rag/api/rag/search with unified error handling and
authentication via auth module. Scoped to citeck-docs repository only.
"""
import ipaddress
import json
import urllib.error
import urllib.request
from urllib.parse import urlparse

from . import auth, config

SEARCH_PATH = "/gateway/rag/api/rag/search"
DEFAULT_TIMEOUT = 30
DOCS_REPO_ID = "citeck-docs"
DEFAULT_TOP_K = 5
# Matches citeck.ai.rag.search.threshold in ecos-ai/application.yml.
# The citeck-rag server default is 0.7 but filters out relevant chunks in practice.
DEFAULT_THRESHOLD = 0.4


class RagApiError(Exception):
    """Base error for RAG API failures."""

    def __init__(self, message, status_code=None, response_body=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class RagAuthenticationError(RagApiError):
    """Raised on 401/403 responses."""


class RagServerError(RagApiError):
    """Raised on 5xx responses."""


class RagConnectionError(RagApiError):
    """Raised when the server is unreachable."""


def resolve_docs_profile(profile=None, config_dir=None):
    """Return the profile name that should handle citeck-docs RAG search.

    Priority:
      1. Explicit `profile` argument.
      2. `docs_profile` field in credentials.json.
      3. Active profile (fallback).

    Raises RagApiError if the resolved profile name doesn't correspond to a
    configured profile.
    """
    resolved = profile or config.get_docs_profile(config_dir) or config.get_active_profile(config_dir)
    creds = config.get_credentials(resolved, config_dir)
    if creds is None:
        docs_profile = config.get_docs_profile(config_dir)
        if docs_profile == resolved:
            raise RagApiError(
                f"Profile '{resolved}' referenced by docs_profile is not configured. "
                "Run '/citeck:citeck-auth' to add it, or call set_docs_profile with a "
                "valid profile name."
            )
        raise RagApiError(
            f"No credentials found for profile '{resolved}'. "
            "Run '/citeck:citeck-auth' to configure."
        )
    return resolved, creds


def _validate_url(url):
    """Reject URLs with unsupported schemes or IPs in link-local/multicast/reserved ranges."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise RagApiError(f"Invalid URL scheme: {parsed.scheme!r}")
    if not parsed.hostname:
        raise RagApiError("URL must contain a hostname")
    try:
        ip = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        return
    if ip.is_link_local or ip.is_multicast or ip.is_reserved:
        raise RagApiError(f"Blocked host: {parsed.hostname}")


def _request(path, body, profile, base_url, config_dir, timeout):
    """POST JSON to the RAG service and return the parsed response."""
    try:
        auth_header = auth.get_auth_header(profile, config_dir)
    except auth.AuthError as e:
        raise RagAuthenticationError(str(e)) from e
    except config.ConfigError as e:
        raise RagApiError(str(e)) from e

    _validate_url(base_url)
    url = base_url.rstrip("/") + path
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
            raise RagAuthenticationError(
                f"Authentication failed: HTTP {e.code} {e.reason}. "
                "Check credentials with '/citeck:citeck-auth'.",
                status_code=e.code,
                response_body=response_body,
            ) from e
        if e.code >= 500:
            raise RagServerError(
                f"RAG server error: HTTP {e.code} {e.reason}",
                status_code=e.code,
                response_body=response_body,
            ) from e
        raise RagApiError(
            f"HTTP {e.code} {e.reason}",
            status_code=e.code,
            response_body=response_body,
        ) from e
    except (urllib.error.URLError, OSError) as e:
        raise RagConnectionError(
            f"Cannot connect to RAG service at {base_url.rstrip('/')}: {e}"
        ) from e


def search_docs(query, top_k=DEFAULT_TOP_K, threshold=DEFAULT_THRESHOLD,
                profile=None, config_dir=None, timeout=DEFAULT_TIMEOUT):
    """Search citeck-docs via RAG.

    Args:
        query: Natural-language question.
        top_k: Max number of results (default: 5).
        threshold: Similarity threshold 0.0-1.0 (default: 0.4, matches ecos-ai config).
        profile: Override the docs profile for this call. Falls back to
                 credentials.docs_profile, then to the active profile.
        config_dir: Config directory override (for tests).
        timeout: Request timeout in seconds.

    Returns:
        List of result dicts as returned by citeck-rag: each has documentId,
        sourceId, content, score, metadata.
    """
    resolved_profile, creds = resolve_docs_profile(profile, config_dir)

    body = {
        "query": query,
        "sourceType": "GITLAB",
        "includeRepoIds": [DOCS_REPO_ID],
        "topK": top_k,
        "threshold": threshold,
    }
    response = _request(SEARCH_PATH, body, resolved_profile, creds["url"], config_dir, timeout)
    if not isinstance(response, list):
        raise RagApiError(
            f"Unexpected RAG response: expected JSON array, got {type(response).__name__}"
        )
    return response
