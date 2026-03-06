#!/usr/bin/env python3
import json
import sys
import os

# Add plugin root to path for lib imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from lib.records_api import request, MUTATE_PATH, RecordsApiError


def main():
    if len(sys.argv) < 2:
        print("Usage: mutate.py '<json-body>'")
        sys.exit(1)

    try:
        body = json.loads(sys.argv[1])
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON argument — {e}")
        sys.exit(1)

    try:
        result = request(MUTATE_PATH, body)
    except RecordsApiError as e:
        print(f"Error: {e}", file=sys.stderr)
        if e.response_body:
            print(f"Response: {e.response_body}", file=sys.stderr)
        sys.exit(1)

    # Summary line
    if "id" in result:
        record_id = result["id"]
        print(f"Mutated record: {record_id}")
    else:
        print("Mutate completed")

    print()
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
