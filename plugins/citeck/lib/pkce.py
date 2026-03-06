"""OIDC Authorization Code Flow with PKCE.

Launches a local HTTP server, opens the browser for Keycloak login,
receives the authorization code via callback, and exchanges it for tokens.
No password is ever stored — only tokens.
"""
import base64
import hashlib
import http.server
import json
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

from .auth import AuthError

CALLBACK_PATH = "/callback"


def generate_pkce_pair():
    """Generate PKCE code_verifier and code_challenge (S256).

    Returns (code_verifier, code_challenge).
    """
    code_verifier = secrets.token_urlsafe(32)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


def generate_state():
    """Generate a random state parameter for CSRF protection."""
    return secrets.token_urlsafe(32)


def _build_authorization_url(auth_endpoint, client_id, redirect_uri,
                              state, code_challenge, scope="openid"):
    """Build the authorization endpoint URL."""
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "scope": scope,
    }
    return auth_endpoint + "?" + urllib.parse.urlencode(params)


def _exchange_code(token_endpoint, code, redirect_uri, client_id, code_verifier):
    """Exchange authorization code for tokens.

    Returns dict with access_token, refresh_token, access_expires_at, refresh_expires_at.
    """
    params = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": code_verifier,
    }
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(
        token_endpoint,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    now = time.time()
    return {
        "access_token": result["access_token"],
        "refresh_token": result.get("refresh_token"),
        "access_expires_at": now + result.get("expires_in", 300),
        "refresh_expires_at": now + result.get("refresh_expires_in", 1800),
    }


SUCCESS_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Citeck ECOS</title></head>
<body style="font-family:sans-serif;text-align:center;padding:60px">
<h2>Authentication successful</h2>
<p>You can close this tab and return to the terminal.</p>
</body></html>"""

ERROR_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Citeck ECOS</title></head>
<body style="font-family:sans-serif;text-align:center;padding:60px">
<h2>Authentication failed</h2>
<p>{error}</p>
</body></html>"""


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Handles the OAuth callback from Keycloak."""

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != CALLBACK_PATH:
            self.send_error(404)
            return

        params = urllib.parse.parse_qs(parsed.query)
        error = params.get("error", [None])[0]
        if error:
            error_desc = params.get("error_description", [error])[0]
            self.server.callback_result = {"error": error_desc}
            self._send_html(400, ERROR_HTML.format(error=error_desc))
            return

        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]

        if not code or not state:
            self.server.callback_result = {"error": "Missing code or state parameter"}
            self._send_html(400, ERROR_HTML.format(error="Missing code or state"))
            return

        self.server.callback_result = {"code": code, "state": state}
        self._send_html(200, SUCCESS_HTML)

    def _send_html(self, status, html):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # Suppress server logs


class CallbackServer:
    """Local HTTP server that waits for the OAuth callback."""

    def __init__(self):
        self._server = http.server.HTTPServer(("127.0.0.1", 0), _CallbackHandler)
        self._server.callback_result = None

    @property
    def port(self):
        return self._server.server_address[1]

    def wait_for_callback(self, timeout=120):
        """Block until callback received or timeout.

        Returns dict with 'code' and 'state', or dict with 'error'.
        Raises AuthError on timeout.
        """
        self._server.timeout = 1
        deadline = time.time() + timeout
        while self._server.callback_result is None:
            if time.time() >= deadline:
                raise AuthError(
                    f"Timed out waiting for browser callback ({timeout}s). "
                    "Please try again."
                )
            self._server.handle_request()
        return self._server.callback_result

    def shutdown(self):
        self._server.server_close()


def authorize(token_endpoint, auth_endpoint, client_id, timeout=120):
    """Run the full PKCE authorization flow.

    1. Start local callback server
    2. Open browser to Keycloak login
    3. Wait for callback with auth code
    4. Exchange code for tokens

    Args:
        token_endpoint: OIDC token endpoint URL
        auth_endpoint: OIDC authorization endpoint URL
        client_id: OIDC client ID
        timeout: Seconds to wait for browser callback

    Returns dict with access_token, refresh_token, access_expires_at, refresh_expires_at.
    Raises AuthError on failure.
    """
    code_verifier, code_challenge = generate_pkce_pair()
    state = generate_state()

    server = CallbackServer()
    try:
        redirect_uri = f"http://127.0.0.1:{server.port}{CALLBACK_PATH}"
        auth_url = _build_authorization_url(
            auth_endpoint, client_id, redirect_uri, state, code_challenge,
        )

        print(f"\nOpen this URL in your browser to log in:\n\n  {auth_url}\n",
              file=sys.stderr)
        try:
            webbrowser.open(auth_url)
        except Exception:
            pass  # Browser open is best-effort; URL is printed above

        result = server.wait_for_callback(timeout)
    finally:
        server.shutdown()

    if "error" in result:
        raise AuthError(f"Authorization failed: {result['error']}")

    if result.get("state") != state:
        raise AuthError("State parameter mismatch — possible CSRF attack.")

    try:
        return _exchange_code(
            token_endpoint, result["code"], redirect_uri, client_id, code_verifier,
        )
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        raise AuthError(
            f"Token exchange failed: HTTP {e.code} {e.reason}"
            + (f" — {body}" if body else "")
        ) from e
    except KeyError as e:
        raise AuthError(f"Unexpected token response: missing field {e}") from e
