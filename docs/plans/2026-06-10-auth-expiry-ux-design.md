# Auth Expiry UX: offline tokens + MCP-initiated re-auth

Date: 2026-06-10
Status: approved

## Problem

When the OIDC PKCE session expires mid-task, MCP tools fail with
`ReauthenticationRequired` and the user must manually run
`/citeck:citeck-auth`, wait for the browser flow, then ask Claude to retry.
Expiry is frequent because the PKCE flow requests only `scope="openid"`,
so the Keycloak refresh token is bound to the SSO session and dies with
its idle timeout (typically ~30 minutes).

## Part A: request `offline_access`

- `pkce.authorize()` gains a `scope` parameter, default
  `"openid offline_access"`. Offline refresh tokens follow Keycloak's
  offline-session policy (30 days idle by default, renewed on each use).
- Graceful fallback: if the client lacks the `offline_access` scope,
  the callback returns `error=invalid_scope`; `authorize()` retries the
  whole flow once with plain `"openid"`.
- `refresh_expires_in: 0` (Keycloak's "never expires" for offline tokens)
  must map to `refresh_expires_at: null` in the token cache — both in
  `pkce._exchange_code` and `auth._refresh_grant`. Cache validity checks
  in `auth.get_auth_header` and `auth._validate_pkce` treat `null` as
  "not expiring". Numeric values keep working (old caches stay valid).
- Unchanged: password-grant (`oidc`), basic auth, `credentials.json`
  format, the citeck-auth skill (it calls the same `pkce.authorize`).

## Part B: `reauthenticate` MCP tool

New tool `reauthenticate(profile=None, timeout=120)` in `citeck_mcp.py`:

1. Resolve profile (active if omitted), load credentials.
2. `auth_method != "oidc-pkce"` → `{ok: false}` with a hint to use the
   citeck-auth skill (basic/password-grant never need browser re-auth).
3. Use stored `token_endpoint`/`authorization_endpoint`; re-discover via
   `discover_oidc_endpoints` if missing.
4. Run `pkce.authorize()` — opens the user's browser, blocks until the
   localhost callback (timeout 120 s).
5. Save tokens via `auth._save_cache`; return `{ok, profile, username, url}`.

Tool docstring instructs the model: call only after a session-expired
error, tell the user a browser window is opening, retry the original
operation on success.

Error contract: `ReauthenticationRequired` message changes from
"Run 'citeck:citeck-auth'" to "Call the `reauthenticate` tool to re-login
via browser, then retry the original operation."

Out of scope (YAGNI): auto-reauth inside regular tools (no surprise
browser pop-ups), MCP elicitation, headless flows.

## Part C: tests and docs

- `test_pkce.py`: default scope includes `offline_access`; invalid_scope
  → one retry with `"openid"`; `refresh_expires_in: 0` → `None`.
- `test_auth.py`: cache with `refresh_expires_at: None` is valid (refresh
  attempted, no `ReauthenticationRequired`); `_refresh_grant` maps 0 →
  `None`; `_validate_pkce` accepts `None`; numeric caches unchanged.
- `test_mcp_server.py`: `reauthenticate` success (mocked
  `pkce.authorize`), basic-auth profile refusal, timeout error,
  endpoint re-discovery.
- Docs: tool list in `CLAUDE.md`, MCP server instructions (call
  `reauthenticate` on session expiry instead of sending the user to
  `/citeck:citeck-auth`), note in `skills/citeck-auth/SKILL.md` that
  simple re-auth of an existing PKCE profile doesn't need the skill.
