"""BPMN checks done by the platform itself: validation and diagram layout.

Both work on a file in the agent's application directory, so a large definition never travels
through the model's context. Outcomes are typed so the agent knows what to do next:

- ``document_error`` / ``layout_rejected``: fix the semantic XML and call again;
- ``service_unavailable``: the platform did not answer; do not regenerate the process;
- ``unknown_after_timeout`` (layout only): the platform layout runs in one shared context and is
  not cancelled on timeout, so after a lost answer its state is unknown; the tool does not retry
  and the agent waits before one more call.

Temporary for stage 1 (plan section 9.7): the retry rule moves into the shared ``app/check``.
"""
import json
import os
import socket
import time

from . import records_api

LAYOUT_PATH = "/gateway/eproc/api/bpmn/auto-layout/transform"
# The platform layout gives up after 60 s; waiting less loses answers that are still coming.
LAYOUT_TIMEOUT = 75
VALIDATE_TIMEOUT = 60
RETRY_PAUSE_SECONDS = 5.0


def _sleep(seconds: float) -> None:
    """Indirection so tests skip real pauses."""
    time.sleep(seconds)


def read_definition(file_path: str) -> tuple[str | None, dict | None]:
    """Read a BPMN file; return (text, None) or (None, error result)."""
    if not file_path:
        return None, {"ok": False, "outcome": "bad_request", "error": "file_path is required."}
    path = os.path.abspath(os.path.expanduser(file_path))
    if not os.path.isfile(path):
        return None, {"ok": False, "outcome": "bad_request", "error": f"File not found: {path}"}
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if not text.strip():
        return None, {"ok": False, "outcome": "bad_request", "error": f"File is empty: {path}"}
    return text, None


def _json_or_none(text: str | None) -> dict | None:
    if not text:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _error_messages(response: dict) -> list[str]:
    result = []
    for message in response.get("messages") or []:
        if str(message.get("level", "")).upper() != "ERROR":
            continue
        msg = message.get("msg")
        if isinstance(msg, dict):
            msg = msg.get("msg") or msg.get("message") or str(msg)
        result.append(str(msg))
    return result


def validate(definition: str, profile=None, config_dir=None) -> dict:
    """Validate a BPMN definition with the platform (``VALIDATE_GENERAL_BPMN``); saves nothing."""
    record = {"id": "eproc/bpmn-def@", "attributes": {
        "action": "VALIDATE_GENERAL_BPMN", "definition": definition}}
    try:
        response = records_api.records_mutate(
            [record], profile=profile, config_dir=config_dir, timeout=VALIDATE_TIMEOUT)
    except records_api.RecordsApiError as e:
        # A rejected document comes back as HTTP 500 with the validation text in the body
        # (checked on a stand 2026-11-10); only a body without error messages is an outage.
        response = _json_or_none(e.response_body)
        if not response or not _error_messages(response):
            return {"ok": False, "outcome": "service_unavailable", "error": str(e),
                    "hint": "The platform did not check the file. Do not rewrite the process because of this."}
    errors = _error_messages(response)
    if errors:
        return {"ok": False, "outcome": "document_error", "errors": errors,
                "hint": "Fix the BPMN file and call bpmn_validate again."}
    return {"ok": True, "outcome": "valid"}


def _is_timeout(error: Exception) -> bool:
    cause = error.__cause__
    reason = getattr(cause, "reason", None)
    return isinstance(cause, (socket.timeout, TimeoutError)) or isinstance(reason, (socket.timeout, TimeoutError)) \
        or "timed out" in str(error).lower()


# Messages of BpmnAutoLayoutService that are about the document itself; any other failure is
# wrapped as "Failed to apply auto-layout: ..." and may hide the platform's own 60 s timeout.
_DOCUMENT_ERRORS = ("BPMN definition cannot be empty", "Invalid BPMN XML format")


def _layout_once(definition: str, profile, config_dir) -> tuple[str, dict]:
    """One layout call: returns (kind, payload) with kind ok|rejected|failed|timeout|unavailable."""
    try:
        response = records_api.request(
            LAYOUT_PATH, {"definition": definition}, profile, config_dir, timeout=LAYOUT_TIMEOUT)
    except records_api.RecordsApiError as e:
        if isinstance(e, records_api.RecordsConnectionError) and _is_timeout(e):
            return "timeout", {"error": str(e)}
        # A gateway timeout or a cut connection behind the gateway may come while the platform still
        # computes the layout: treat it as a timeout, not as an unreachable service.
        if getattr(e, "status_code", None) in (502, 504):
            return "timeout", {"error": str(e)}
        return "unavailable", {"error": str(e)}
    if response.get("success") and response.get("definition"):
        return "ok", {"definition": response["definition"], "message": response.get("message")}
    message = response.get("message") or "Layout failed without a message."
    if any(message.startswith(prefix) for prefix in _DOCUMENT_ERRORS):
        return "rejected", {"error": message}
    return "failed", {"error": message}


def layout(definition: str, profile=None, config_dir=None) -> dict:
    """Lay out the BPMN diagram with the platform.

    Only an unreachable service is retried (once, after a pause): a timeout or a failure inside the
    layout may leave the computation running in the platform's shared context, so a second call
    could overlap it. Returns {"ok": True, "definition": ...} or a typed failure.
    """
    kind, payload = _layout_once(definition, profile, config_dir)
    attempts = 1
    if kind == "unavailable":
        _sleep(RETRY_PAUSE_SECONDS)
        kind, payload = _layout_once(definition, profile, config_dir)
        attempts = 2
    if kind == "ok":
        return {"ok": True, "outcome": "laid_out", "attempts": attempts, **payload}
    if kind == "rejected":
        return {"ok": False, "outcome": "layout_rejected", "attempts": attempts, "error": payload["error"],
                "hint": "The document is not BPMN XML. Fix the file and run bpmn_validate before bpmn_layout."}
    if kind in ("timeout", "failed"):
        return {"ok": False, "outcome": "unknown_after_timeout" if kind == "timeout" else "layout_failed",
                "attempts": attempts, "error": payload["error"],
                "hint": "The platform may still be computing this layout (its timeout is reported the same "
                        "way). Run bpmn_validate; if the file is valid, do not call bpmn_layout for two "
                        "minutes, then call it once. If it fails again, stop and report the process without "
                        "a diagram."}
    return {"ok": False, "outcome": "service_unavailable", "attempts": attempts, "error": payload["error"],
            "hint": "The layout service did not answer. Do not regenerate the process because of this."}
