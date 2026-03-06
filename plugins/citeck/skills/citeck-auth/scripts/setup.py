#!/usr/bin/env python3
"""Save Citeck ECOS credentials to a profile."""
import argparse
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from lib import config
from lib import auth


def main():
    parser = argparse.ArgumentParser(description="Configure Citeck ECOS credentials")
    parser.add_argument("--profile", default="default", help="Profile name (default: default)")
    parser.add_argument("--url", required=True, help="Citeck ECOS base URL")
    parser.add_argument("--username", required=True, help="Username")
    parser.add_argument("--password", default=None,
                        help="[deprecated: use CITECK_PASSWORD env var] Password")
    parser.add_argument("--client-id", default=None,
                        help="[deprecated: use CITECK_CLIENT_ID env var] OIDC client ID")
    parser.add_argument("--client-secret", default=None,
                        help="[deprecated: use CITECK_CLIENT_SECRET env var] OIDC client secret")
    parser.add_argument("--auth-method", default="oidc", choices=["oidc", "basic"],
                        help="Auth method (default: oidc)")
    args = parser.parse_args()

    url = args.url.rstrip("/")
    password = os.environ.get("CITECK_PASSWORD") or args.password
    client_id = os.environ.get("CITECK_CLIENT_ID") or args.client_id
    client_secret = os.environ.get("CITECK_CLIENT_SECRET") or args.client_secret
    config_dir = os.environ.get("CITECK_CONFIG_DIR")

    if not password:
        print(json.dumps({"status": "error", "error": "Password required: set CITECK_PASSWORD env var"}), file=sys.stderr)
        sys.exit(1)

    # Discover OIDC endpoints from eis.json
    eis_id = None
    realm = None
    token_endpoint = None
    authorization_endpoint = None

    if args.auth_method == "oidc":
        print("Discovering OIDC endpoints...", file=sys.stderr)
        eis_info = auth.discover_eis(url)
        eis_id = eis_info["eis_id"]
        realm = eis_info["realm"]

        if not eis_info["is_oidc"]:
            print(f"Server does not support OIDC (eisId={eis_id}), using basic auth", file=sys.stderr)
            args.auth_method = "basic"
        else:
            endpoints = auth.discover_oidc_endpoints(eis_id, realm)
            if endpoints:
                token_endpoint = endpoints["token_endpoint"]
                authorization_endpoint = endpoints["authorization_endpoint"]
                print(f"Discovered Keycloak: realm={realm}, eis_id={eis_id}", file=sys.stderr)
            else:
                print(f"Warning: Could not discover OIDC endpoints, will use fallback", file=sys.stderr)

    try:
        config.save_credentials(
            profile=args.profile,
            url=url,
            username=args.username,
            password=password,
            client_id=client_id,
            client_secret=client_secret,
            auth_method=args.auth_method,
            realm=realm,
            eis_id=eis_id,
            token_endpoint=token_endpoint,
            authorization_endpoint=authorization_endpoint,
            config_dir=config_dir,
        )
        result = {
            "status": "ok",
            "profile": args.profile,
            "url": url,
            "username": args.username,
            "auth_method": args.auth_method,
        }
        if realm:
            result["realm"] = realm
        if eis_id:
            result["eis_id"] = eis_id
        print(json.dumps(result, indent=2))
    except config.ConfigError as e:
        print(json.dumps({"status": "error", "error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
