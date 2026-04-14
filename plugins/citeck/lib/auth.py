"""OIDC + Basic Auth module for Citeck ECOS API.

Uses config.py for credentials instead of hardcoded values.
Discovers Keycloak endpoints via eis.json + OpenID Connect well-known configuration.
Caches tokens per-profile in ~/.citeck/tokens/{profile}/token.json.
"""
import base64
import json
import os
import stat
import sys
import time
import urllib.request
import urllib.error
import urllib.parse

from . import config

TOKEN_EXPIRY_MARGIN = 30
DEFAULT_REALM = "ecos-app"
DEFAULT_EIS_ID = "EIS_ID"
EIS_JSON_PATH = "/eis.json"
WELL_KNOWN_PATH_TEMPLATE = "/auth/realms/{realm}/.well-known/openid-configuration"
# Fallback for local instances without eis.json discovery
FALLBACK_TOKEN_PATH = "/ecos-idp/auth/realms/{realm}/protocol/openid-connect/token"
LOCALHOST_IDP_PREFIX = "/ecos-idp"


def _token_cache_path(profile, config_dir=None):
    config._validate_profile_name(profile)
    d = config_dir or config.DEFAULT_CONFIG_DIR
    return os.path.join(d, "tokens", profile, "token.json")


def _load_cache(profile, config_dir=None):
    path = _token_cache_path(profile, config_dir)
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _save_cache(data, profile, config_dir=None):
    path = _token_cache_path(profile, config_dir)
    dir_path = os.path.dirname(path)
    os.makedirs(dir_path, exist_ok=True)
    os.chmod(dir_path, stat.S_IRWXU)  # 700
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)


def _eis_id_to_base_url(eis_id):
    """Convert eisId to a base URL, adding protocol if needed."""
    if eis_id.startswith("http"):
        return eis_id.rstrip("/")
    if eis_id.startswith("localhost"):
        return "http://" + eis_id.rstrip("/")
    return "https://" + eis_id.rstrip("/")


def _is_localhost(url):
    """Check if URL points to localhost."""
    stripped = url.rstrip("/")
    return (stripped == "http://localhost"
            or stripped.startswith("http://localhost:")
            or stripped.startswith("http://127.0.0.1"))


def discover_eis(base_url):
    """Fetch eis.json from the server.

    Returns dict with 'eis_id', 'realm', and 'is_oidc' keys.
    For localhost with unconfigured eis.json, probes the local Keycloak
    at /ecos-idp before falling back to non-OIDC.
    """
    url = base_url.rstrip("/") + EIS_JSON_PATH
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            eis_id = data.get("eisId", DEFAULT_EIS_ID)
            realm = data.get("realmId", DEFAULT_REALM)
            if eis_id != DEFAULT_EIS_ID:
                return {"eis_id": eis_id, "realm": realm, "is_oidc": True}
    except (urllib.error.URLError, urllib.error.HTTPError, OSError,
            json.JSONDecodeError, KeyError):
        eis_id = DEFAULT_EIS_ID
        realm = DEFAULT_REALM

    # eis.json returned placeholder values — probe local Keycloak for localhost
    if _is_localhost(base_url):
        probe_url = (base_url.rstrip("/") + LOCALHOST_IDP_PREFIX
                     + WELL_KNOWN_PATH_TEMPLATE.format(realm=DEFAULT_REALM))
        try:
            probe_req = urllib.request.Request(probe_url, method="GET")
            with urllib.request.urlopen(probe_req, timeout=5) as resp:
                json.loads(resp.read().decode("utf-8"))
                # Keycloak is reachable — treat as OIDC-capable
                return {
                    "eis_id": base_url.rstrip("/"),
                    "realm": DEFAULT_REALM,
                    "is_oidc": True,
                }
        except (urllib.error.URLError, urllib.error.HTTPError, OSError,
                json.JSONDecodeError, KeyError):
            pass

    return {"eis_id": DEFAULT_EIS_ID, "realm": DEFAULT_REALM, "is_oidc": False}


def _fix_localhost_endpoint(endpoint, base_url):
    """Fix Keycloak endpoint URLs for localhost behind reverse proxy.

    Keycloak's well-known config returns internal paths (e.g. /realms/...)
    that may not be routed by the nginx proxy. Replace with the /ecos-idp/auth
    proxied path.
    """
    from urllib.parse import urlparse
    parsed = urlparse(endpoint)
    path = parsed.path
    # If path doesn't already include /ecos-idp, add the prefix
    if not path.startswith(LOCALHOST_IDP_PREFIX):
        new_path = LOCALHOST_IDP_PREFIX + "/auth" + path
        return base_url.rstrip("/") + new_path
    return endpoint


def discover_oidc_endpoints(eis_id, realm):
    """Fetch OpenID Connect well-known configuration.

    For localhost eis_id, tries /ecos-idp prefix first (local Keycloak behind proxy)
    and fixes returned endpoint URLs to use the proxied path.
    Returns dict with 'token_endpoint' and 'authorization_endpoint',
    or None if discovery fails.
    """
    keycloak_url = _eis_id_to_base_url(eis_id)
    is_local = _is_localhost(keycloak_url)

    # For localhost, try /ecos-idp prefix first (Keycloak behind reverse proxy)
    urls_to_try = []
    if is_local:
        urls_to_try.append(keycloak_url + LOCALHOST_IDP_PREFIX
                           + WELL_KNOWN_PATH_TEMPLATE.format(realm=realm))
    urls_to_try.append(keycloak_url + WELL_KNOWN_PATH_TEMPLATE.format(realm=realm))

    for well_known_url in urls_to_try:
        req = urllib.request.Request(well_known_url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                token_ep = data["token_endpoint"]
                auth_ep = data["authorization_endpoint"]
                # Fix endpoints for localhost proxy
                if is_local:
                    token_ep = _fix_localhost_endpoint(token_ep, keycloak_url)
                    auth_ep = _fix_localhost_endpoint(auth_ep, keycloak_url)
                return {
                    "token_endpoint": token_ep,
                    "authorization_endpoint": auth_ep,
                }
        except (urllib.error.URLError, urllib.error.HTTPError, OSError,
                json.JSONDecodeError, KeyError):
            continue
    return None


def _get_token_endpoint(creds):
    """Derive OIDC token endpoint from credentials.

    Uses stored token_endpoint if available, otherwise falls back to
    constructing URL from base URL + realm.
    """
    if creds.get("token_endpoint"):
        return creds["token_endpoint"]
    url = creds["url"].rstrip("/")
    realm = creds.get("realm", DEFAULT_REALM)
    return url + FALLBACK_TOKEN_PATH.format(realm=realm)


def _get_auth_endpoint(creds):
    """Get OIDC authorization endpoint from credentials.

    Uses stored authorization_endpoint if available, otherwise falls back to
    constructing URL from base URL + realm.
    """
    if creds.get("authorization_endpoint"):
        return creds["authorization_endpoint"]
    url = creds["url"].rstrip("/")
    realm = creds.get("realm", DEFAULT_REALM)
    fallback = "/ecos-idp/auth/realms/{realm}/protocol/openid-connect/auth"
    return url + fallback.format(realm=realm)


def _token_request(endpoint, params):
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _password_grant(creds):
    endpoint = _get_token_endpoint(creds)
    params = {
        "grant_type": "password",
        "username": creds["username"],
        "password": creds["password"],
    }
    if creds.get("client_id"):
        params["client_id"] = creds["client_id"]
    if creds.get("client_secret"):
        params["client_secret"] = creds["client_secret"]
    result = _token_request(endpoint, params)
    now = time.time()
    return {
        "access_token": result["access_token"],
        "refresh_token": result.get("refresh_token"),
        "access_expires_at": now + result.get("expires_in", 300),
        "refresh_expires_at": now + result.get("refresh_expires_in", 1800),
    }


def _refresh_grant(creds, refresh_token):
    endpoint = _get_token_endpoint(creds)
    params = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    if creds.get("client_id"):
        params["client_id"] = creds["client_id"]
    if creds.get("client_secret"):
        params["client_secret"] = creds["client_secret"]
    result = _token_request(endpoint, params)
    now = time.time()
    return {
        "access_token": result["access_token"],
        "refresh_token": result.get("refresh_token", refresh_token),
        "access_expires_at": now + result.get("expires_in", 300),
        "refresh_expires_at": now + result.get("refresh_expires_in", 1800),
    }


def _basic_auth_header(username, password):
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {token}"


class AuthError(Exception):
    """Raised when authentication fails and no fallback is available."""


class ReauthenticationRequired(AuthError):
    """Raised when PKCE session expires and browser re-auth is needed."""


def get_auth_header(profile=None, config_dir=None):
    """Return an Authorization header value (Bearer or Basic).

    1. Load credentials from config
    2. Try cached access token
    3. Try refresh grant
    4. Try password grant
    5. Fall back to Basic Auth on connection errors
    """
    creds, resolved_profile = _resolve_credentials(profile, config_dir)
    auth_method = creds.get("auth_method", "oidc")

    if auth_method == "basic":
        return _basic_auth_header(creds["username"], creds["password"])

    now = time.time()
    cache = _load_cache(resolved_profile, config_dir)

    if cache and cache.get("access_expires_at", 0) > now + TOKEN_EXPIRY_MARGIN:
        return f"Bearer {cache['access_token']}"

    if (cache and cache.get("refresh_token")
            and cache.get("refresh_expires_at", 0) > now + TOKEN_EXPIRY_MARGIN):
        try:
            cache = _refresh_grant(creds, cache["refresh_token"])
            _save_cache(cache, resolved_profile, config_dir)
            return f"Bearer {cache['access_token']}"
        except (urllib.error.HTTPError, urllib.error.URLError, OSError, KeyError):
            pass  # Refresh failed; fall through

    if auth_method == "oidc-pkce":
        raise ReauthenticationRequired(
            f"Session expired for profile '{resolved_profile}'. "
            "Run 'citeck:citeck-auth' to re-authenticate via browser."
        )

    try:
        cache = _password_grant(creds)
        _save_cache(cache, resolved_profile, config_dir)
        return f"Bearer {cache['access_token']}"
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        raise AuthError(
            f"OIDC authentication failed: HTTP {e.code} {e.reason}"
            + (f" — {body}" if body else "")
        ) from e
    except KeyError as e:
        raise AuthError(f"Unexpected OIDC response: missing field {e}") from e
    except (urllib.error.URLError, OSError):
        print("Warning: OIDC unavailable, falling back to Basic Auth", file=sys.stderr)
        return _basic_auth_header(creds["username"], creds["password"])


def validate_connection(profile=None, config_dir=None):
    """Test credentials by attempting OIDC password grant or Basic Auth request.

    Returns dict with 'ok' (bool), 'method' (str), and 'error' (str or None).
    """
    creds, resolved_profile = _resolve_credentials(profile, config_dir)
    auth_method = creds.get("auth_method", "oidc")

    if auth_method == "basic":
        return _validate_basic(creds)

    if auth_method == "oidc-pkce":
        return _validate_pkce(resolved_profile, config_dir)

    try:
        cache = _password_grant(creds)
        _save_cache(cache, resolved_profile, config_dir)
        return {"ok": True, "method": "oidc", "error": None}
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, KeyError) as e:
        return {"ok": False, "method": "oidc", "error": str(e)}


def _validate_basic(creds):
    """Validate basic auth by making a test request to the Records API."""
    url = creds["url"].rstrip("/") + "/gateway/api/records/query"
    auth_val = _basic_auth_header(creds["username"], creds["password"])
    body = json.dumps({"sourceId": "", "query": {}, "attributes": {}}).encode()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Authorization": auth_val, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp.read()
        return {"ok": True, "method": "basic", "error": None}
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return {"ok": False, "method": "basic", "error": f"HTTP {e.code} {e.reason}"}
        # Non-auth HTTP errors (e.g. 400, 500) mean auth succeeded but query failed
        return {"ok": True, "method": "basic", "error": None}
    except (urllib.error.URLError, OSError) as e:
        return {"ok": False, "method": "basic", "error": str(e)}


def _validate_pkce(profile, config_dir=None):
    """Validate PKCE auth by checking for a valid cached token."""
    now = time.time()
    cache = _load_cache(profile, config_dir)
    if cache and cache.get("access_expires_at", 0) > now + TOKEN_EXPIRY_MARGIN:
        return {"ok": True, "method": "oidc-pkce", "error": None}
    if (cache and cache.get("refresh_token")
            and cache.get("refresh_expires_at", 0) > now + TOKEN_EXPIRY_MARGIN):
        return {"ok": True, "method": "oidc-pkce", "error": None}
    return {
        "ok": False, "method": "oidc-pkce",
        "error": "No valid token cached. Run 'citeck:citeck-auth' to authenticate.",
    }


def _resolve_credentials(profile, config_dir):
    """Resolve credentials and profile name. Raises AuthError if not configured."""
    resolved_profile = profile or config.get_active_profile(config_dir)
    creds = config.get_credentials(resolved_profile, config_dir)
    if creds is None:
        raise AuthError(
            f"No credentials found for profile '{resolved_profile}'. "
            "Run 'citeck:citeck-auth' to configure."
        )
    return creds, resolved_profile


def _decode_jwt_payload(token):
    """Decode the payload (middle segment) of a JWT without verification."""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    payload_b64 = parts[1]
    padding = 4 - len(payload_b64) % 4
    if padding != 4:
        payload_b64 += "=" * padding
    try:
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        return json.loads(payload_bytes)
    except (ValueError, json.JSONDecodeError):
        return None


def get_username(profile=None, config_dir=None):
    """Return the username for the current profile.

    For basic auth: returns the stored username from credentials.
    For oidc/oidc-pkce: decodes the cached JWT access token payload
    to extract preferred_username.
    Returns None if username cannot be determined.
    """
    creds, resolved_profile = _resolve_credentials(profile, config_dir)

    if creds.get("username"):
        return creds["username"]

    auth_method = creds.get("auth_method", "oidc")
    if auth_method in ("oidc", "oidc-pkce"):
        cache = _load_cache(resolved_profile, config_dir)
        if cache and cache.get("access_token"):
            payload = _decode_jwt_payload(cache["access_token"])
            if payload:
                return payload.get("preferred_username")

    return None
