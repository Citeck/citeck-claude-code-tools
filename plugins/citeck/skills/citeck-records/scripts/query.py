#!/usr/bin/env python3
import json
import sys
import urllib.request
import urllib.error
from auth import get_auth_header

BASE_URL = "http://localhost/gateway/api/records/query"
AUTH = get_auth_header()


def main():
    if len(sys.argv) < 2:
        print("Usage: query.py '<json-body>'")
        sys.exit(1)

    try:
        body = json.loads(sys.argv[1])
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON argument — {e}")
        sys.exit(1)

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        BASE_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": AUTH,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"Error: HTTP {e.code} {e.reason}")
        print(f"Response: {error_body}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Error: Cannot connect to Citeck — {e.reason}")
        print("Is Citeck running on localhost? Check: http://localhost")
        sys.exit(1)

    # Summary line
    if "records" in result:
        count = len(result["records"])
        print(f"Found {count} record{'s' if count != 1 else ''}")
    elif "id" in result or "attributes" in result:
        print("Loaded record")
    else:
        print("Done")

    print()
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
