---
name: citeck-auth
description: "Configure Citeck ECOS connection - set URL, credentials, and test connectivity. Use when the user needs to set up or manage Citeck authentication."
allowed-tools: Bash(python3 */skills/citeck-auth/scripts/setup.py *, python3 */skills/citeck-auth/scripts/setup_pkce.py *, python3 */skills/citeck-auth/scripts/test_connection.py *, python3 */skills/citeck-auth/scripts/switch_profile.py *), AskUserQuestion
---

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
python3 ${CLAUDE_SKILL_DIR}/scripts/setup_pkce.py --profile <name> --url <url> [--client-id <id>] [--timeout 120]
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
CITECK_PASSWORD='<pass>' python3 ${CLAUDE_SKILL_DIR}/scripts/setup.py --profile <name> --url <url> --username <user> [--auth-method oidc|basic]
```

For OIDC auth with client credentials:
```bash
CITECK_PASSWORD='<pass>' CITECK_CLIENT_ID='<id>' CITECK_CLIENT_SECRET='<secret>' python3 ${CLAUDE_SKILL_DIR}/scripts/setup.py --profile <name> --url <url> --username <user>
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

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/test_connection.py [--profile <name>]
```

Reports whether the connection succeeded, which auth method was used, and any errors.

### 3. Switch Active Profile

Switch between configured profiles:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/switch_profile.py --profile <name>
```

Lists available profiles when called with `--list`.

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/switch_profile.py --list
```

## Setup Flow

When a user needs to configure Citeck ECOS access:

1. Ask for the Citeck ECOS URL (e.g., http://localhost, https://citeck.example.com)
2. Ask which auth method they prefer:
   - **PKCE (recommended)** — browser-based, no password stored
   - **Password grant** — username/password required
   - **Basic auth** — username/password, no OIDC
3. Ask for profile name (default: "default")
4. **If PKCE:**
   - Optionally ask for client_id (default: `citeck-ai-agent`)
   - Run `setup_pkce.py` — it discovers endpoints and prints a URL, show it to the user via AskUserQuestion
   - The user logs in via browser, tokens are received automatically
5. **If Password grant or Basic:**
   - Ask for username and password
   - If OIDC: optionally ask for client_id and client_secret
   - Run `setup.py` passing secrets via environment variables
6. Run `test_connection.py` to verify the connection
7. Report the result to the user

## Re-authentication

When a PKCE session expires (both access and refresh tokens), skills will report a `ReauthenticationRequired` error. In that case, re-run this skill to authenticate again via browser.

## Credentials Storage

Credentials are stored in `~/.citeck/credentials.json` with restricted permissions (chmod 600, owner-only access).
Tokens are cached per-profile in `~/.citeck/tokens/{profile}/token.json`.

Profile entries include discovered OIDC metadata:
- `realm` — Keycloak realm name
- `eis_id` — Keycloak host identifier
- `token_endpoint` — Full URL to the OIDC token endpoint
- `authorization_endpoint` — Full URL to the OIDC authorization endpoint

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
