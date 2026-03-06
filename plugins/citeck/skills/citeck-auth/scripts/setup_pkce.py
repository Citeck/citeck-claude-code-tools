#!/usr/bin/env python3
"""Set up Citeck ECOS authentication via browser-based OIDC PKCE flow."""
import argparse
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from lib import config
from lib import auth
from lib import pkce


def main():
    parser = argparse.ArgumentParser(
        description="Authenticate to Citeck ECOS via browser (OIDC PKCE)")
    parser.add_argument("--profile", default="default",
                        help="Profile name (default: default)")
    parser.add_argument("--url", required=True,
                        help="Citeck ECOS base URL")
    parser.add_argument("--client-id", default=None,
                        help="OIDC public client ID (default: CITECK_CLIENT_ID env or 'citeck-ai-agent')")
    parser.add_argument("--timeout", type=int, default=120,
                        help="Seconds to wait for browser callback (default: 120)")
    args = parser.parse_args()

    url = args.url.rstrip("/")
    client_id = args.client_id or os.environ.get("CITECK_CLIENT_ID", "citeck-ai-agent")
    config_dir = os.environ.get("CITECK_CONFIG_DIR")

    # Discover OIDC endpoints from eis.json
    print("Discovering OIDC endpoints...", file=sys.stderr)
    eis_info = auth.discover_eis(url)
    eis_id = eis_info["eis_id"]
    realm = eis_info["realm"]

    if not eis_info["is_oidc"]:
        print(json.dumps({
            "status": "error",
            "error": f"Server does not support OIDC (eisId={eis_id}). "
                     "Use password-based setup with --auth-method basic instead.",
        }), file=sys.stderr)
        sys.exit(1)

    token_endpoint = None
    authorization_endpoint = None

    endpoints = auth.discover_oidc_endpoints(eis_id, realm)
    if endpoints:
        token_endpoint = endpoints["token_endpoint"]
        authorization_endpoint = endpoints["authorization_endpoint"]
        print(f"Discovered Keycloak: realm={realm}, eis_id={eis_id}", file=sys.stderr)
    else:
        print(json.dumps({
            "status": "error",
            "error": "Could not discover OIDC endpoints from Keycloak. "
                     "Check that the server is reachable.",
        }), file=sys.stderr)
        sys.exit(1)

    try:
        tokens = pkce.authorize(
            token_endpoint, authorization_endpoint, client_id,
            timeout=args.timeout,
        )
    except auth.AuthError as e:
        print(json.dumps({"status": "error", "error": str(e)}), file=sys.stderr)
        sys.exit(1)

    try:
        config.save_credentials(
            profile=args.profile,
            url=url,
            client_id=client_id,
            auth_method="oidc-pkce",
            realm=realm,
            eis_id=eis_id,
            token_endpoint=token_endpoint,
            authorization_endpoint=authorization_endpoint,
            config_dir=config_dir,
        )
        auth._save_cache(tokens, args.profile, config_dir)

        result = {
            "status": "ok",
            "profile": args.profile,
            "url": url,
            "auth_method": "oidc-pkce",
            "realm": realm,
            "eis_id": eis_id,
        }
        print(json.dumps(result, indent=2))
    except (config.ConfigError, OSError) as e:
        print(json.dumps({"status": "error", "error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
