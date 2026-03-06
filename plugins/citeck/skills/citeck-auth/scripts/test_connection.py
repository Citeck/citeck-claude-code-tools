#!/usr/bin/env python3
"""Test Citeck ECOS connection using saved credentials."""
import argparse
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from lib import auth
from lib import config


def main():
    parser = argparse.ArgumentParser(description="Test Citeck ECOS connection")
    parser.add_argument("--profile", default=None, help="Profile name (default: active profile)")
    args = parser.parse_args()

    config_dir = os.environ.get("CITECK_CONFIG_DIR")
    profile_name = args.profile or config.get_active_profile(config_dir)

    try:
        result = auth.validate_connection(profile=profile_name, config_dir=config_dir)
        result["profile"] = profile_name

        creds = config.get_credentials(profile_name, config_dir)
        if creds:
            result["url"] = creds.get("url", "")
            result["username"] = creds.get("username", "")

        print(json.dumps(result, indent=2))
        if not result["ok"]:
            sys.exit(1)
    except auth.AuthError as e:
        print(json.dumps({"ok": False, "error": str(e), "profile": profile_name}), file=sys.stderr)
        sys.exit(1)
    except config.ConfigError as e:
        print(json.dumps({"ok": False, "error": str(e), "profile": profile_name}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
