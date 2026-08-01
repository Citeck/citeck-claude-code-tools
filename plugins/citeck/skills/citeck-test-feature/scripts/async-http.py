#!/usr/bin/env python3
"""Fail-closed helper for Citeck-style asynchronous HTTP endpoints."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


class ContractError(RuntimeError):
    pass


def auth_headers() -> dict[str, str]:
    basic = os.environ.get("BASIC_AUTH", "")
    bearer = os.environ.get("BEARER_TOKEN", "")
    if basic and bearer:
        raise ContractError("Set only BASIC_AUTH or BEARER_TOKEN, not both")
    if basic:
        token = base64.b64encode(basic.encode()).decode()
        return {"Authorization": f"Basic {token}"}
    if bearer:
        return {"Authorization": f"Bearer {bearer}"}
    return {}


def request_json(method: str, url: str, data: bytes | None = None) -> tuple[int, dict]:
    headers = {"Accept": "application/json", **auth_headers()}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = response.status
            body = response.read()
    except urllib.error.HTTPError as error:
        status = error.code
        body = error.read()
    except urllib.error.URLError as error:
        raise ContractError(f"{method} {url} failed: {error.reason}") from error

    try:
        payload = json.loads(body.decode() or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        preview = body[:300].decode(errors="replace")
        raise ContractError(f"{method} {url} returned invalid JSON (HTTP {status}): {preview}") from error
    if not isinstance(payload, dict):
        raise ContractError(f"{method} {url} returned non-object JSON (HTTP {status})")
    return status, payload


def submit(args: argparse.Namespace) -> dict:
    data = Path(args.data_file).read_bytes()
    status, payload = request_json("POST", args.url, data)
    if status != args.expected_status:
        raise ContractError(f"submit expected HTTP {args.expected_status}, got {status}: {payload}")
    request_id = payload.get(args.request_id_key)
    if not isinstance(request_id, str) or not request_id:
        raise ContractError(f"submit response has no non-empty '{args.request_id_key}': {payload}")
    return payload


def poll(args: argparse.Namespace) -> dict:
    for attempt in range(1, args.attempts + 1):
        status, payload = request_json("GET", args.url)
        if status == args.processing_status:
            if attempt < args.attempts:
                time.sleep(args.interval)
            continue
        if status == args.success_status:
            if args.result_key and args.result_key not in payload:
                raise ContractError(
                    f"terminal response has no '{args.result_key}' (HTTP {status}): {payload}"
                )
            return payload
        raise ContractError(f"poll returned unexpected HTTP {status}: {payload}")
    raise ContractError(f"poll timeout after {args.attempts} attempts: {args.url}")


def cancel(args: argparse.Namespace) -> dict:
    status, payload = request_json("DELETE", args.url)
    if status not in args.expected_status:
        expected = ",".join(str(item) for item in args.expected_status)
        raise ContractError(f"cancel expected HTTP {expected}, got {status}: {payload}")
    return payload


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)

    submit_parser = subparsers.add_parser("submit")
    submit_parser.add_argument("--url", required=True)
    submit_parser.add_argument("--data-file", required=True)
    submit_parser.add_argument("--expected-status", type=int, default=202)
    submit_parser.add_argument("--request-id-key", default="requestId")
    submit_parser.set_defaults(handler=submit)

    poll_parser = subparsers.add_parser("poll")
    poll_parser.add_argument("--url", required=True)
    poll_parser.add_argument("--attempts", type=int, default=60)
    poll_parser.add_argument("--interval", type=float, default=2)
    poll_parser.add_argument("--processing-status", type=int, default=202)
    poll_parser.add_argument("--success-status", type=int, default=200)
    poll_parser.add_argument("--result-key", default="result")
    poll_parser.set_defaults(handler=poll)

    cancel_parser = subparsers.add_parser("cancel")
    cancel_parser.add_argument("--url", required=True)
    cancel_parser.add_argument("--expected-status", type=int, nargs="+", default=[200, 204])
    cancel_parser.set_defaults(handler=cancel)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        payload = args.handler(args)
    except (ContractError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
