#!/usr/bin/env python3
"""OIDC + Basic Auth module for Citeck ECOS API.

Attempts OIDC password grant first, falls back to Basic Auth if Keycloak is unavailable.
Caches tokens in ~/.citeck/token.json between invocations.
"""
import json
import os
import time
import urllib.request
import urllib.error
import urllib.parse

TOKEN_ENDPOINT = "http://localhost/ecos-idp/auth/realms/ecos-app/protocol/openid-connect/token"
CLIENT_ID = "sqa"
CLIENT_SECRET = "6RmiEmvuwvrNVPYx8TlKVP0XZffnoacf"
USERNAME = "admin"
PASSWORD = "admin"

BASIC_AUTH = "Basic YWRtaW46YWRtaW4="
TOKEN_CACHE_PATH = os.path.expanduser("~/.citeck/token.json")
TOKEN_EXPIRY_MARGIN = 30


def _load_cache():
    try:
        with open(TOKEN_CACHE_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _save_cache(data):
    os.makedirs(os.path.dirname(TOKEN_CACHE_PATH), exist_ok=True)
    with open(TOKEN_CACHE_PATH, "w") as f:
        json.dump(data, f, indent=2)


def _token_request(params):
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(
        TOKEN_ENDPOINT,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _password_grant():
    result = _token_request({
        "grant_type": "password",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "username": USERNAME,
        "password": PASSWORD,
    })
    now = time.time()
    return {
        "access_token": result["access_token"],
        "refresh_token": result.get("refresh_token"),
        "access_expires_at": now + result.get("expires_in", 300),
        "refresh_expires_at": now + result.get("refresh_expires_in", 1800),
    }


def _refresh_grant(refresh_token):
    result = _token_request({
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token,
    })
    now = time.time()
    return {
        "access_token": result["access_token"],
        "refresh_token": result.get("refresh_token", refresh_token),
        "access_expires_at": now + result.get("expires_in", 300),
        "refresh_expires_at": now + result.get("refresh_expires_in", 1800),
    }


def get_auth_header():
    """Return an Authorization header value (Bearer or Basic).

    1. Try cached access token
    2. Try refresh grant
    3. Try password grant
    4. Fall back to Basic Auth on connection errors
    """
    now = time.time()
    cache = _load_cache()

    if cache and cache.get("access_expires_at", 0) > now + TOKEN_EXPIRY_MARGIN:
        return f"Bearer {cache['access_token']}"

    try:
        if (cache and cache.get("refresh_token")
                and cache.get("refresh_expires_at", 0) > now + TOKEN_EXPIRY_MARGIN):
            cache = _refresh_grant(cache["refresh_token"])
            _save_cache(cache)
            return f"Bearer {cache['access_token']}"

        cache = _password_grant()
        _save_cache(cache)
        return f"Bearer {cache['access_token']}"

    except (urllib.error.URLError, urllib.error.HTTPError, OSError, KeyError):
        return BASIC_AUTH
