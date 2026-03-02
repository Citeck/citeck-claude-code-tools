#!/usr/bin/env python3
import json
import sys
import urllib.request
import urllib.error

BASE_URL = "http://localhost/gateway/api/records/delete"
AUTH = "Basic YWRtaW46YWRtaW4="


def main():
    if len(sys.argv) < 2:
        print("Usage: delete.py '<json-body>'")
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
    records = body.get("records", [])
    count = len(records)
    print(f"Deleted {count} record{'s' if count != 1 else ''}")

    print()
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
