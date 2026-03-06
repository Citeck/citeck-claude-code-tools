# Citeck ECOS Plugin for Claude Code

Plugin for interacting with Citeck ECOS instances from Claude Code CLI.

## Authentication

The plugin supports three auth methods:
- **OIDC PKCE** (recommended) — browser-based login, no password stored
- **OIDC Password Grant** — username/password
- **Basic Auth** — for instances without Keycloak

### OIDC Endpoint Discovery

When setting up a profile, the plugin automatically discovers OIDC endpoints:

1. Fetches `{server_url}/eis.json` → gets `eisId` (Keycloak host) and `realmId`
2. Fetches `https://{eisId}/auth/realms/{realmId}/.well-known/openid-configuration` → gets token and authorization endpoints
3. Stores discovered endpoints in the profile

This means Keycloak can be on a different host than the application (e.g., app at `citeck.example.com`, Keycloak at `eis.example.com`).

## Keycloak Client Setup (for PKCE auth)

PKCE flow requires a **public** Keycloak client configured for localhost redirects. Follow these steps to create one.

> **Which realm?** Create the client in the realm returned by `eis.json` (`realmId` field).
> For cloud instances this is typically `Infrastructure` — the shared realm where all server clients live
> (e.g., `citeck.example.com`, `citeck-idea-plugin`). User authentication goes through this realm.

### Step 1 — Create Client

In Keycloak Admin Console → select the correct realm → Clients → Create:

| Field | Value |
|-------|-------|
| **Client ID** | `citeck-ai-agent` |
| **Client Protocol** | `openid-connect` |
| **Root URL** | _(leave empty)_ |

Click **Save**.

### Step 2 — Configure Client

On the client Settings tab:

| Field | Value |
|-------|-------|
| **Access Type** | `public` |
| **Standard Flow Enabled** | `ON` |
| **Direct Access Grants Enabled** | `OFF` |
| **Valid Redirect URIs** | `http://127.0.0.1/*` |
| **Web Origins** | `+` |

### Step 3 — Session Timeouts (Advanced Settings)

At the bottom of the Settings tab, expand **Advanced Settings**:

| Field | Value        | Description |
|-------|--------------|-------------|
| **Access Token Lifespan** | `30 minutes` | How long the access token is valid |
| **Client Session Idle** | `8 hours`    | Refresh token expires after this idle time |
| **Client Session Max** | `14 days`    | Maximum session duration (re-login after this) |

### Security Notes

- **Public client** — no client_secret to leak
- **PKCE S256** — protects against authorization code interception
- **localhost-only redirect** — tokens only delivered to local machine
- **Tokens stored with `chmod 600`** — owner-only read access in `~/.citeck/`
- **30-min access token** — limits exposure window if token is compromised
- **24h session max** — forces periodic re-authentication

## Usage

Setup authentication:
```bash
# PKCE (recommended) — opens browser for login
/citeck:citeck-auth

# Or manually:
python3 scripts/setup_pkce.py --url https://citeck.example.com --client-id citeck-ai-agent
```

The `client_id` defaults to the server hostname if not specified.

## Custom Agents

The plugin includes two custom agents that Claude can delegate to automatically:

### citeck-explorer

Read-only agent for exploring Citeck ECOS data via Records API. Automatically used when investigating records, searching data, or exploring record structure.

- Tools: Bash, Read, Grep, Glob (read-only, no Write/Edit)
- Preloaded skill: citeck-records

### citeck-manager

Agent for managing Citeck Project Tracker issues — creating, updating, and searching tasks. Automatically used for multi-step tracker operations.

- Tools: Bash, Read, Grep, Glob, AskUserQuestion
- Preloaded skill: citeck-tracker
- All mutations require dry-run preview and user confirmation before execution

## Development

Run tests:
```bash
cd plugins/citeck
python3 -m pytest tests/ -v
```
