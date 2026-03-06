#!/usr/bin/env python3
"""Switch or list Citeck ECOS profiles."""
import argparse
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from lib import config


def main():
    parser = argparse.ArgumentParser(description="Switch or list Citeck ECOS profiles")
    parser.add_argument("--profile", default=None, help="Profile to switch to")
    parser.add_argument("--list", action="store_true", help="List available profiles")
    args = parser.parse_args()

    config_dir = os.environ.get("CITECK_CONFIG_DIR")

    if args.list:
        profiles = config.get_profiles(config_dir)
        active = config.get_active_profile(config_dir)
        result = {
            "profiles": profiles,
            "active": active,
        }
        print(json.dumps(result, indent=2))
        return

    if args.profile is None:
        active = config.get_active_profile(config_dir)
        profiles = config.get_profiles(config_dir)
        print(json.dumps({"active": active, "profiles": profiles}, indent=2))
        return

    try:
        config.set_active_profile(args.profile, config_dir)
        print(json.dumps({
            "status": "ok",
            "active_profile": args.profile,
        }, indent=2))
    except config.ConfigError as e:
        print(json.dumps({"status": "error", "error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
