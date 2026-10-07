---
name: citeck-auth
description: "Configure Citeck ECOS connection - set URL, credentials, and test connectivity. Use when the user needs to set up or manage Citeck authentication."
allowed-tools: >-
  Bash(python3 "${CLAUDE_SKILL_DIR}/scripts/setup_pkce.py"*),
  Bash(python3 "${CLAUDE_SKILL_DIR}/scripts/setup.py"*),
  Bash(CITECK_PASSWORD=* python3 "${CLAUDE_SKILL_DIR}/scripts/setup.py"*),
  Bash(python3 "${CLAUDE_SKILL_DIR}/scripts/test_connection.py"*),
  Bash(python3 "${CLAUDE_SKILL_DIR}/scripts/switch_profile.py"*),
  AskUserQuestion,
  mcp__plugin_citeck_citeck__list_profiles,
  mcp__plugin_citeck_citeck__test_connection,
  mcp__plugin_citeck_citeck__set_docs_profile,
  mcp__plugin_citeck_citeck__set_ept_profile,
  mcp__plugin_citeck_citeck__set_records_profile,
  mcp__plugin_citeck_citeck__reauthenticate
---

## Client compatibility

Shared by Claude Code and Codex.
- Skill directory: `${CLAUDE_SKILL_DIR}`. Claude Code substitutes it; if it appears unexpanded,
  use the absolute directory containing this `SKILL.md`.
- Quote script paths and run each script command as shown, one per call, without loops or
  shell variables: Claude Code pre-approves exactly these forms.
- MCP tools are named without the client prefix.
- User-question mechanism: `AskUserQuestion` in Claude Code; elsewhere the client's question
  tool, or ask in chat and wait for the answer.

# Citeck ECOS Authentication Setup

Configure and manage connections to Citeck ECOS instances. Supports multiple profiles for different environments.

## Endpoint Discovery

Setup scripts automatically discover OIDC endpoints:

1. Fetch `{url}/eis.json` → get `eisId` and `realmId`
2. If `eisId == "EIS_ID"` → no Keycloak, use Basic Auth
3. Otherwise, `eisId` is the Keycloak host (may differ from app URL), `realmId` is the realm
4. Fetch `https://{eisId}/auth/realms/{realmId}/.well-known/openid-configuration` → get actual token/auth endpoints
5. Store discovered endpoints in the profile for runtime use

This means Keycloak can live on a different host (e.g., app at `citeck.example.com`, Keycloak at `eis.example.com`).

## Operations

### 1. Setup Credentials (Browser-based PKCE — Recommended)

Authenticate via browser without storing passwords. The script opens a browser for Keycloak login and receives tokens automatically:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/setup_pkce.py" --profile <name> --url <url> [--client-id <id>] [--timeout 120]
```

Parameters:
- `--profile` — Profile name (default: "default")
- `--url` — Citeck ECOS base URL (e.g., http://localhost, https://citeck.example.com)
- `--client-id` — OIDC public client ID (default: from CITECK_CLIENT_ID env or `citeck-ai-agent`)
- `--timeout` — Seconds to wait for browser callback (default: 120)

The script will:
1. Discover OIDC endpoints via `eis.json`
2. Print a URL — show it to the user so they can open it in their browser
3. After login, tokens are saved automatically — no password is stored

### 1b. Setup Credentials (Password-based)

For environments without browser access, use password-based setup:

```bash
CITECK_PASSWORD='<pass>' python3 "${CLAUDE_SKILL_DIR}/scripts/setup.py" --profile <name> --url <url> --username <user> [--auth-method oidc|basic]
```

For OIDC auth with client credentials:
```bash
CITECK_PASSWORD='<pass>' CITECK_CLIENT_ID='<id>' CITECK_CLIENT_SECRET='<secret>' python3 "${CLAUDE_SKILL_DIR}/scripts/setup.py" --profile <name> --url <url> --username <user>
```

Parameters:
- `--profile` — Profile name (default: "default")
- `--url` — Citeck ECOS base URL (e.g., http://localhost)
- `--username` — Username for authentication
- `--auth-method` — Authentication method: "oidc" (default) or "basic"

Environment variables (preferred over CLI args to avoid process-list exposure):
- `CITECK_PASSWORD` — Password for authentication (required)
- `CITECK_CLIENT_ID` — OIDC client ID (optional, for OIDC auth)
- `CITECK_CLIENT_SECRET` — OIDC client secret (optional, for OIDC auth)

### 2. Test Connection

Validate saved credentials by testing connectivity:

Prefer the MCP tools when available: call `list_profiles`, verify that the selected
profile is active and its URL matches the requested target, then call `test_connection`.
This tool has no `profile` argument: verify the returned profile and URL too. Do not
switch a shared active profile just to perform a check. For a different profile, or
when MCP is unavailable, use the script below with an explicit profile. Shell HTTP
and local callback ports may require client approval; if the sandbox blocks them,
request that approval when supported or report the limitation. Never silently widen
permissions or treat a blocked request as invalid credentials.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/test_connection.py" [--profile <name>]
```

Reports whether the connection succeeded, which auth method was used, and any errors.

### 3. Switch Active Profile

Switch between configured profiles:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/switch_profile.py" --profile <name>
```

Lists available profiles when called with `--list`.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/switch_profile.py" --list
```

Show non-sensitive settings (url, auth_method, client_id) of a specific profile:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/switch_profile.py" --detail <name>
```

## Setup Flow

When a user needs to configure or re-authenticate Citeck ECOS access:

### Step 1: Check for existing profiles

Run `switch_profile.py --list` to check if profiles already exist.

### Step 2a: Existing profiles found (most common — re-authentication)

1. Show the user their profiles and which one is active
2. Run `switch_profile.py --detail <active_profile>` to get the active profile's settings (url, auth_method, client_id)
3. Ask the user what they want:
   - **Re-authenticate the current profile** (default) — just refresh tokens using saved settings
   - **Switch to a different profile** — run `switch_profile.py --profile <name>`
   - **Set up a new profile** — go to Step 2b
4. **Re-authenticate PKCE profile:** run `setup_pkce.py` with url and client_id from the existing profile — do NOT ask the user for URL or auth method again
5. **Re-authenticate password profile:** ask only for the password (it may have changed), run `setup.py` with url and username from the existing profile
6. Verify the connection using the MCP or script procedure in “Test Connection” above
7. Report the result

### Step 2b: No profiles exist (first-time setup)

1. Ask for the Citeck ECOS URL (e.g., http://localhost, https://citeck.example.com)
2. Ask which auth method they prefer:
   - **PKCE (recommended)** — browser-based, no password stored
   - **Password grant** — username/password required
   - **Basic auth** — username/password, no OIDC
3. Ask for profile name (default: "default")
4. **If PKCE:**
   - Optionally ask for client_id (default: `citeck-ai-agent`)
   - Run `setup_pkce.py` — it discovers endpoints and prints a URL, show it to the user using the available user-question mechanism
   - The user logs in via browser, tokens are received automatically
5. **If Password grant or Basic:**
   - Ask for username and password
   - If OIDC: optionally ask for client_id and client_secret
   - Run `setup.py` passing secrets via environment variables
6. Verify the connection using the MCP or script procedure in “Test Connection” above
7. Report the result to the user
8. **Optional: mark this profile as the docs source.** Ask using the available user-question mechanism:
   > **Use this profile as the citeck-docs source for the `citeck-ask-docs` skill?**
   > Options: "Yes", "No"

   Only suggest "Yes" if this profile plausibly hosts the citeck-docs RAG index (typically a production or shared server, not an empty local instance). If confirmed, call `set_docs_profile(profile: "<name>")`.

9. **Optional: mark this profile as the task-tracker source.** Ask using the available user-question mechanism:
   > **Use this profile for task-tracker tools (search_issues, create_issue, query_comments, etc.)?**
   > Options: "Yes", "No"

   Suggest "Yes" when the user typically works with the tracker on this environment but may run records queries elsewhere (e.g. tracker on production, records on local). If confirmed, call `set_ept_profile(profile: "<name>")`.

10. **Optional: mark this profile for plain records queries.** Ask using the available user-question mechanism:
    > **Use this profile for plain `records_query` / `records_mutate`?**
    > Options: "Yes", "No"

    Suggest "Yes" when the user typically runs records queries on this environment but uses the tracker elsewhere. If confirmed, call `set_records_profile(profile: "<name>")`.

## Re-authentication

When a PKCE session expires (both access and refresh tokens), prefer the MCP tool `reauthenticate` — it opens the browser and refreshes tokens for an existing profile without re-running this skill. This skill is for first-time setup, changing URLs/credentials, and managing profiles. Use it for re-authentication only when the MCP server is unavailable or the profile is password-based.

## Credentials Storage

Credentials are stored in `~/.citeck/credentials.json` with restricted permissions (chmod 600, owner-only access).
Tokens are cached per-profile in `~/.citeck/tokens/{profile}/token.json`.

Profile entries include discovered OIDC metadata:
- `realm` — Keycloak realm name
- `eis_id` — Keycloak host identifier
- `token_endpoint` — Full URL to the OIDC token endpoint
- `authorization_endpoint` — Full URL to the OIDC authorization endpoint

Top-level fields `docs_profile`, `ept_profile`, and `records_profile` (each separate from `active_profile`) route specific tool groups to a chosen profile. If unset, each falls back to the active profile. See plugin README for the full mapping.

If you need to verify permissions manually:
```bash
ls -la ~/.citeck/credentials.json
# Should show: -rw------- (600)
```

## Notes

- If credentials are not configured, other citeck skills will prompt the user to run this skill first
- PKCE profiles store only URL and client_id — no password on disk
- Password-based profiles store passwords in plaintext (acceptable for local dev environments)
- Multiple profiles allow managing different environments (local, staging, production)
- OIDC endpoints are auto-discovered; Keycloak may be on a different host than the app
