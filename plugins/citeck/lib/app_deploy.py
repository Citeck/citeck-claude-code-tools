"""Deploy an ``ecos-apps`` application directory into one workspace and wait for the result.

The application is zipped and uploaded through Records (``eapps/ecosapp@`` with ``_workspace``
and ``_content``) - the platform's own upload, which binds the app and its artifacts to the
workspace (``EcosAppService.uploadZip``). The plugin knows nothing about artifact kinds.

When this upload has finished is not exposed by the platform API, nor is the error text of a
failed artifact. Both are read from the ``ecos-apps`` container log (stage-1 local stands):
``Start artifacts uploading from source`` for the app's source key, then ``Create new artifact
revision`` for every changed artifact in that trace, then ``Deploy status changed ...`` per
artifact; errors follow ``Artifact deploy failed: <kind>$<id>. Errors:`` as JSON lines, import
errors are ``Artifacts can't be received`` / ``Artifact uploading failed``. Log lines name an
artifact without its workspace, so every result read from the log is confirmed against the
workspace-scoped Records state of this app's own artifacts. Without the log the end of the upload
cannot be confirmed and the result says so instead of claiming success.

The scope checks here are temporary for stage 1 (plan section 9.7) and are a convenience, not a
security boundary.
"""
import base64
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import time
import zipfile
from datetime import datetime, timedelta, timezone

import yaml

from . import guards, records_api

GEN_WORKSPACE_ENV = "CITECK_GEN_WORKSPACE"
EAPPS_LOG_CMD_ENV = "CITECK_EAPPS_LOG_CMD"

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
USER_RE = re.compile(r"^[A-Za-z0-9._@-]{1,100}$")
# Workspaces the platform treats as global (WorkspaceServiceImpl.isWorkspaceWithGlobalEntities).
GLOBAL_WORKSPACES = {"default"}
TERMINAL = ("DEPLOYED", "DEPLOY_FAILED")
POLL_SECONDS = 3.0
DEFAULT_WAIT_SECONDS = 240
# A failed artifact is retried by the platform about every 25 s; wait for one retry before
# reporting, since a dependency deployed later may let the retry succeed.
FAILED_RETRY_WAIT_SECONDS = 45
# How long a started upload may stay without any artifact change before it is reported as such.
NO_CHANGES_QUIET_SECONDS = 15.0
# Records `_modified` and log times come from the same stand; allow for rounding only.
CLOCK_SLACK_SECONDS = 0.2
EARLIER_ERRORS_MINUTES = 60

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_ENTRY_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}\.\d+)\s+(?P<level>[A-Z]+)\s+\[[^\]]*\]\s+"
    r"\[(?P<trace>[^\]]*)\]\s+\[[^\]]*\]\s+\S+\s*:\s(?P<msg>.*)$")
_UPLOAD_RE = re.compile(r"Upload application '(?P<app>[^']+)'")
_UNCHANGED_RE = re.compile(r"Application content doesn't change\. App ID: '(?P<app>[^']+)'")
_START_RE = re.compile(r"Start artifacts uploading from source .*SourceKey\(id=(?P<src>[^,]+), type=ECOS_APP\)")
_IMPORT_FAILED_RE = re.compile(
    r"(?:Artifacts can't be received from source|Artifact uploading failed\. Source): "
    r".*SourceKey\(id=(?P<src>[^,]+), type=ECOS_APP\)\)?(?P<rest>.*)$")
_REVISION_RE = re.compile(
    r"Create new artifact revision entity .*\((?P<ref>[a-z-]+/[a-z0-9-]+\$[^)\s]+)\)\. "
    r"Source: SourceKey\(id=(?P<src>[^,]+),")
_STATUS_RE = re.compile(r"Deploy status changed for (?P<ref>\S+) from (?P<from>\w+) to (?P<to>\w+)")
_FAILED_RE = re.compile(r"Artifact deploy failed: (?P<ref>\S+?)\. Errors:")
_EMODEL_TYPE_OUTSIDE_RE = re.compile(r"emodel/type@(?!CURRENT_WS:)[A-Za-z0-9_$:.-]+")
_REF_RE = re.compile(
    r"\b(?P<src>[a-z][a-z0-9-]*/(?:(?P<srcws>[A-Za-z0-9_-]+):)?[a-z][a-z0-9-]*)@(?P<local>[A-Za-z0-9_$:.-]*)")

_WORKSPACE_REF = "emodel/workspace@"

_SKIP_NAMES = {".git", ".DS_Store", "__MACOSX", ".citeck-deploy"}


class DeployError(Exception):
    """A deploy refused before anything was uploaded."""


class UploadRejected(Exception):
    """The platform refused the upload itself (before any artifact was deployed)."""


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- application directory

def read_meta(app_dir: str) -> dict:
    path = os.path.join(app_dir, "meta.json")
    if not os.path.isfile(path):
        raise DeployError(f"No meta.json in {app_dir}: an ecos-apps application needs meta.json "
                          "with id, name and version next to the artifacts/ directory.")
    try:
        with open(path, encoding="utf-8") as f:
            meta = json.load(f)
    except ValueError as e:
        raise DeployError(f"meta.json is not valid JSON: {e}") from e
    app_id = str(meta.get("id", ""))
    if not ID_RE.match(app_id):
        raise DeployError(f"Application id '{app_id}' in meta.json must match {ID_RE.pattern} "
                          "(no workspace prefix: the workspace is given separately).")
    if not os.path.isdir(os.path.join(app_dir, "artifacts")):
        raise DeployError(f"No artifacts/ directory in {app_dir}.")
    return meta


def _files(app_dir: str, *kind: str):
    base = os.path.join(app_dir, "artifacts", *kind)
    for root, _, files in os.walk(base):
        for name in sorted(files):
            path = os.path.join(root, name)
            with open(path, encoding="utf-8", errors="replace") as f:
                yield os.path.relpath(path, app_dir), f.read()


def _own_prefix(local: str, ws_ids: set[str]) -> bool:
    prefix, sep, _ = local.partition(":")
    return bool(sep) and (prefix == "CURRENT_WS" or prefix in ws_ids)


def _load(text: str):
    """Parse a JSON or YAML artifact file; None when it is neither."""
    try:
        return json.loads(text)
    except ValueError:
        pass
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        return None


def _patch_targets(data) -> tuple[list[str], list[str]]:
    """(record refs a `mutate` patch writes, `_workspace` values it sets) from `config.records`.

    Only the operation's own targets count: refs inside the written attributes (a type's
    association target, a form ref) are data, not targets.
    """
    if not isinstance(data, dict):
        return [], []
    config = data.get("config") if isinstance(data.get("config"), dict) else {}
    records = config.get("records") or data.get("records") or []
    if not isinstance(records, list):
        records = [records]
    single = config.get("record") or data.get("record")
    if single:
        # MutateRecordsPatchExecutor also takes one `record`.
        records = list(records) + [single]
    refs, workspaces = [], []
    for record in records if isinstance(records, list) else []:
        if isinstance(record, str):
            refs.append(record)
            continue
        if not isinstance(record, dict):
            continue
        if record.get("id"):
            refs.append(str(record["id"]))
        attributes = record.get("attributes") if isinstance(record.get("attributes"), dict) else {}
        for key, value in attributes.items():
            name = key.split("?", 1)[0]
            if name == "_workspace" and value:
                workspaces.append(str(value).split("@", 1)[-1])
            elif name == "_parent" and str(value).startswith(_WORKSPACE_REF):
                # A record whose parent is a workspace (a member, for one) lands in that workspace.
                workspaces.append(str(value)[len(_WORKSPACE_REF):])
    return refs, workspaces


def check_artifact_scope(app_dir: str, ws_ids: set[str] | None = None) -> list[str]:
    """Content checks that keep the app inside its workspace (temporary, plan section 9.7).

    ``ws_ids`` holds the workspace id and its system id.
    """
    ws_ids = set(ws_ids or ())
    problems = []
    if os.path.isdir(os.path.join(app_dir, "artifacts", "model", "workspace")):
        problems.append("artifacts/model/workspace: the application must not create workspaces; "
                        "deploy_app creates the target workspace itself.")
    for kind in (("model", "permissions"), ("model", "permission-settings")):
        for rel, text in _files(app_dir, *kind):
            # Any occurrence counts: a permissions artifact names only the type it replaces rights of.
            for match in _EMODEL_TYPE_OUTSIDE_RE.finditer(text):
                problems.append(
                    f"{rel}: {match.group(0)} is outside the workspace; a permissions artifact replaces "
                    "the permissions of the type it names. Use emodel/type@CURRENT_WS:<id>.")
    for rel, text in _files(app_dir, "app", "artifact-patch"):
        data = _load(text)
        value = data.get("workspace") if isinstance(data, dict) else None
        if not value or str(value) not in ws_ids:
            problems.append(
                f"{rel}: an artifact patch applies in the workspace written in its `workspace` field "
                f"(empty means global). Set `workspace: {sorted(ws_ids)[0] if ws_ids else '<ws>'}`.")
    for rel, text in _files(app_dir, "app", "patch"):
        data = _load(text)
        if data is None:
            problems.append(f"{rel}: not valid YAML or JSON.")
            continue
        refs, workspaces = _patch_targets(data)
        for ws in workspaces:
            if ws not in ws_ids:
                problems.append(f"{rel}: workspace {ws} (in _workspace or _parent) is not this workspace.")
        for target in refs:
            if target.startswith(_WORKSPACE_REF) and target[len(_WORKSPACE_REF):] not in ws_ids:
                problems.append(f"{rel}: {target} is another workspace; a patch may change only this one.")
                continue
            match = _REF_RE.search(target)
            if not match:
                continue
            ref, local, src_ws = match.group(0), match.group("local"), match.group("srcws")
            foreign_ws = (":" in local and not _own_prefix(local, ws_ids)) or bool(src_ws and src_ws not in ws_ids)
            global_artifact = guards.is_artifact_source(ref) and not _own_prefix(local, ws_ids)
            if foreign_ws or global_artifact:
                problems.append(f"{rel}: {ref} is outside the workspace; a patch may change only records "
                                "and artifacts of this workspace.")
    return problems


def build_zip(app_dir: str) -> bytes:
    """Zip meta.json and artifacts/ in a stable order, skipping VCS and service files."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        entries = ["meta.json"]
        for root, dirs, files in os.walk(os.path.join(app_dir, "artifacts")):
            dirs[:] = sorted(d for d in dirs if d not in _SKIP_NAMES and not d.startswith("."))
            for name in sorted(files):
                if name in _SKIP_NAMES or name.startswith("."):
                    continue
                entries.append(os.path.relpath(os.path.join(root, name), app_dir))
        for rel in entries:
            info = zipfile.ZipInfo(rel.replace(os.sep, "/"), date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            with open(os.path.join(app_dir, rel), "rb") as f:
                zf.writestr(info, f.read())
    return buffer.getvalue()


# ---------------------------------------------------------------- stand side

def _attr(response: dict, name: str):
    records = response.get("records") or []
    if not records:
        return None
    return (records[0].get("attributes") or {}).get(name)


def _exists(ref: str, profile=None, config_dir=None) -> bool:
    """Whether a record exists. ``id`` is no test: some sources echo it for a missing record."""
    response = records_api.records_load([ref], {"missing": "_notExists?bool"},
                                        profile=profile, config_dir=config_dir)
    return bool(response.get("records")) and _attr(response, "missing") is not True


def resolve_workspace(workspace: str | None) -> tuple[str, bool]:
    """Return (workspace, configured) from the argument and CITECK_GEN_WORKSPACE."""
    configured = (os.environ.get(GEN_WORKSPACE_ENV) or "").strip()
    ws = (workspace or "").strip() or configured
    if not ws:
        raise DeployError(f"Give the target workspace id (or set {GEN_WORKSPACE_ENV}).")
    if configured and ws != configured:
        raise DeployError(f"Workspace '{ws}' is not the generation workspace '{configured}' "
                          f"({GEN_WORKSPACE_ENV}); deploying elsewhere is refused.")
    if not ID_RE.match(ws):
        raise DeployError(f"Workspace id '{ws}' must match {ID_RE.pattern}.")
    if ws in GLOBAL_WORKSPACES:
        raise DeployError(f"Workspace '{ws}' holds global entities on the platform; "
                          "deploy only into a separate generation workspace.")
    return ws, bool(configured)


def check_app_id_free_globally(app_id: str, profile=None, config_dir=None) -> None:
    if _exists(f"eapps/ecosapp@{app_id}", profile, config_dir):
        raise DeployError(f"'{app_id}' is the id of an application installed on the stand; "
                          "choose another application id in meta.json.")


def ensure_workspace(ws: str, app_id: str, name: dict | str | None, configured: bool,
                     profile=None, config_dir=None) -> bool:
    """Create the workspace if absent; refuse a foreign one. Returns True when created."""
    if _exists(f"emodel/workspace@{ws}", profile, config_dir):
        if not configured:
            apps = records_api.records_query(
                "eapps/ecosapp", query={}, language="predicate", attributes={"id": "id"},
                workspaces=[ws], page={"maxItems": 50}, profile=profile, config_dir=config_dir)
            others = sorted({str((r.get("attributes") or {}).get("id")) for r in apps.get("records") or []}
                            - {app_id})
            if others:
                raise DeployError(f"Workspace '{ws}' already holds other applications ({', '.join(others)}); "
                                  "deploy only into a workspace made for this application.")
        return False
    title = name if isinstance(name, dict) and name else {"ru": str(name or ws), "en": str(name or ws)}
    created = _mutate([{"id": "emodel/workspace@", "attributes": {
        "id": ws, "name": title, "visibility": "PRIVATE"}}], profile=profile, config_dir=config_dir)
    _raise_messages(created, f"Cannot create workspace '{ws}'")
    return True


def workspace_system_id(ws: str, profile=None, config_dir=None) -> str:
    """The platform's system id of the workspace: the prefix of ids inside it (may differ from ws)."""
    response = records_api.records_load([f"emodel/workspace@{ws}"], {"sys": "systemId?str"},
                                        profile=profile, config_dir=config_dir)
    return str(_attr(response, "sys") or ws)


def ensure_members(ws: str, members: list[str], profile=None, config_dir=None) -> list[str]:
    """Add users as ordinary members of the workspace; returns the users added now."""
    if not members:
        return []
    bad = [m for m in members if not USER_RE.match(m)]
    if bad:
        raise DeployError(f"Bad user names: {', '.join(bad)}")
    response = records_api.records_load([f"emodel/workspace@{ws}"], {"m": "workspaceMembers[]?json"},
                                        profile=profile, config_dir=config_dir)
    present = set()
    for member in _attr(response, "m") or []:
        for authority in member.get("authorities") or []:
            present.add(str(authority).split("@", 1)[-1])
    added = []
    for user in members:
        if user in present:
            continue
        result = _mutate([{"id": "emodel/workspace-member@", "attributes": {
            "_parent": f"emodel/workspace@{ws}", "_parentAtt": "workspaceMembers",
            "memberId": f"gen-member-{user}", "authorities": [f"emodel/person@{user}"],
            "memberRole": "USER"}}], profile=profile, config_dir=config_dir)
        _raise_messages(result, f"Cannot add member '{user}'")
        added.append(user)
    return added


def _mutate(records: list[dict], profile=None, config_dir=None) -> dict:
    """records_mutate that returns the platform's error messages instead of raising on HTTP 500.

    The Records API answers a refused mutation with HTTP 500 and the reason in the body.
    """
    try:
        return records_api.records_mutate(records, profile=profile, config_dir=config_dir)
    except records_api.RecordsApiError as e:
        try:
            body = json.loads(e.response_body or "")
        except ValueError:
            body = None
        if isinstance(body, dict) and body.get("messages"):
            return body
        raise


def _error_texts_of(response: dict) -> list[str]:
    errors = []
    for message in response.get("messages") or []:
        if str(message.get("level", "")).upper() == "ERROR":
            msg = message.get("msg")
            errors.append(str(msg.get("msg") if isinstance(msg, dict) else msg))
    return errors


def _raise_messages(response: dict, prefix: str) -> None:
    errors = _error_texts_of(response)
    if errors:
        raise DeployError(f"{prefix}: {'; '.join(errors)}")


def upload(zip_bytes: bytes, ws: str, profile=None, config_dir=None) -> str:
    """Upload the archive into the workspace; returns the app record id the platform answered.

    Right after a workspace is created (or after a lookup of a missing one) ecos-apps may still
    cache it as missing and answer ``eapps/ecosapp@DELETED_<ws>:<app>`` (seen on a stand
    2026-11-10). The app is stored in the real workspace all the same and processed under the
    source key ``DELETED_<ws>:<app>``, so the answer is used as it is.
    """
    content = "data:application/zip;base64," + base64.b64encode(zip_bytes).decode("ascii")
    response = _mutate([{"id": "eapps/ecosapp@", "attributes": {
        "_workspace": ws, "_content": [{"url": content}]}}], profile=profile, config_dir=config_dir)
    errors = _error_texts_of(response)
    if errors:
        raise UploadRejected("; ".join(errors))
    records = response.get("records") or []
    return str(records[0].get("id", "")) if records else ""


def query_artifacts(app_id: str, ws: str, ws_sys: str, profile=None, config_dir=None) -> list[dict]:
    response = records_api.records_query(
        "eapps/artifact", query={"t": "eq", "a": "ecosApp", "v": app_id}, language="predicate",
        attributes={"id": "?localId", "status": "deployStatus", "modified": "_modified"},
        workspaces=[ws], page={"maxItems": 1000}, profile=profile, config_dir=config_dir)
    result = []
    for record in response.get("records") or []:
        attrs = record.get("attributes") or {}
        result.append({"artifact": _bare_ref(str(attrs.get("id") or record.get("id", "")), ws_sys),
                       "status": attrs.get("status"), "modified": attrs.get("modified")})
    return result


def _bare_ref(ref: str, ws_sys: str) -> str:
    """'eapps/artifact@ui/form$ws:id' or 'ui/form$ws:id' -> 'ui/form$id'."""
    ref = ref.split("@", 1)[1] if ref.startswith("eapps/artifact@") else ref
    kind, _, local = ref.partition("$")
    if local.startswith(ws_sys + ":"):
        local = local[len(ws_sys) + 1:]
    return f"{kind}${local}" if local else ref


# ---------------------------------------------------------------- log

def log_command(since: str) -> list[str] | None:
    """The command printing the ecos-apps log since a time, or None when unavailable."""
    template = (os.environ.get(EAPPS_LOG_CMD_ENV) or "").strip()
    if template:
        return [part.replace("{since}", since) for part in shlex.split(template)]
    docker = shutil.which("docker")
    if not docker:
        return None
    try:
        names = subprocess.run([docker, "ps", "--filter", "name=citeck_eapps_", "--format", "{{.Names}}"],
                               capture_output=True, text=True, timeout=15).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return None
    if len(names) != 1:
        return None
    return [docker, "logs", "--since", since, names[0]]


def read_log(command: list[str]) -> list[str] | None:
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    # docker logs replays the container's stdout and stderr on its own two streams.
    return done.stdout.splitlines() + done.stderr.splitlines()


def _entries(lines: list[str]) -> list[dict]:
    """Group log lines into entries (a header line plus its continuation lines)."""
    entries: list[dict] = []
    for raw in lines:
        line = _ANSI_RE.sub("", raw).rstrip("\n")
        match = _ENTRY_RE.match(line)
        if match:
            entries.append({"ts": match.group("ts"), "trace": match.group("trace"),
                            "msg": match.group("msg"), "extra": []})
        elif entries and line.strip():
            entries[-1]["extra"].append(line)
    entries.sort(key=lambda e: e["ts"])
    return entries


def _error_texts(extra: list[str]) -> list[str]:
    texts = []
    for line in extra:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
        except ValueError:
            texts.append(line[:500])
            continue
        if isinstance(data, dict):
            texts.append(str(data.get("message") or data.get("type") or line[:500]))
    return texts


def _exception_text(extra: list[str]) -> str | None:
    """The first line of a logged stack trace (``SomeException: message``)."""
    for line in extra:
        line = line.strip()
        if line and not line.startswith("at "):
            return line[:500]
    return None


def parse_upload_log(lines: list[str], source_key: str, app_id: str) -> dict:
    """What the log says about one upload of ``source_key`` (``<ws sys id>:<app>``).

    Returns {"unchanged", "started", "changed": [ref], "own_changed": {ref revisions of this
    source}, "changed_at": {ref: log time (UTC) the artifact was queued}, "status": {ref: last
    status after it was queued, DRAFT included}, "failed_count": {ref: n}, "errors": {ref: [text]},
    "import_errors": [text]}; refs are ``kind$id`` without the workspace. Status lines carry no
    workspace: the caller confirms them against Records.
    """
    result = {"unchanged": False, "started": False, "changed": [], "own_changed": set(), "changed_at": {},
              "status": {}, "failed_count": {}, "errors": {}, "import_errors": []}
    start_trace = None
    upload_trace = None
    changed_at: dict[str, int] = {}
    entries = _entries(lines)
    # The log is read from a little before this upload: everything before the latest upload request
    # of this app belongs to an earlier deploy (seen live: a deploy one second earlier).
    uploads = [i for i, e in enumerate(entries)
               if (m := _UPLOAD_RE.search(e["msg"])) and m.group("app") == app_id]
    first = uploads[-1] if uploads else 0
    for index, entry in enumerate(entries):
        if index < first:
            continue
        msg = entry["msg"]
        match = _UPLOAD_RE.search(msg)
        if match and match.group("app") == app_id:
            upload_trace = entry["trace"]
            continue
        match = _UNCHANGED_RE.search(msg)
        if match and match.group("app") == app_id and entry["trace"] == upload_trace:
            result["unchanged"] = True
            continue
        match = _START_RE.search(msg)
        if match and match.group("src") == source_key:
            result["started"] = True
            start_trace = entry["trace"]
            continue
        match = _IMPORT_FAILED_RE.search(msg)
        if match and match.group("src") == source_key:
            text = (match.group("rest") or "").strip()
            cause = _exception_text(entry["extra"])
            result["import_errors"].append(" ".join(t for t in (text, cause) if t) or msg[:500])
            continue
        match = _REVISION_RE.search(msg)
        if match and match.group("src") == source_key and entry["trace"] == start_trace:
            ref = match.group("ref")
            if ref not in changed_at:
                result["changed"].append(ref)
            changed_at[ref] = index
            result["own_changed"].add(ref)
            result["changed_at"][ref] = _log_time(entry["ts"])
            result["status"][ref] = "DRAFT"
            continue
        match = _FAILED_RE.search(msg)
        if match and match.group("ref") in changed_at and index > changed_at[match.group("ref")]:
            texts = _error_texts(entry["extra"]) or ["The platform logged no error text."]
            result["errors"][match.group("ref")] = texts  # the latest attempt's text
            continue
        match = _STATUS_RE.search(msg)
        if not match:
            continue
        ref, new = match.group("ref"), match.group("to")
        if new == "DRAFT" and start_trace and entry["trace"] == start_trace and ref not in changed_at:
            # An artifact whose revision already exists is re-queued without a revision line; it may
            # belong to another app of the same watcher pass, so the caller checks it is ours.
            result["changed"].append(ref)
            changed_at[ref] = index
            result["changed_at"][ref] = _log_time(entry["ts"])
        if ref in changed_at and index >= changed_at[ref]:
            result["status"][ref] = new  # the latest state wins: a retry resets a failure
            if new == "DEPLOY_FAILED":
                result["failed_count"][ref] = result["failed_count"].get(ref, 0) + 1
    return result


def last_errors(lines: list[str], refs: list[str]) -> dict[str, list[str]]:
    """The latest logged error texts of each artifact in ``refs`` (``kind$id``)."""
    wanted = set(refs)
    found: dict[str, list[str]] = {}
    for entry in _entries(lines):
        match = _FAILED_RE.search(entry["msg"])
        if match and match.group("ref") in wanted:
            found[match.group("ref")] = _error_texts(entry["extra"]) or ["The platform logged no error text."]
    return found


# ---------------------------------------------------------------- wait

def _parse_time(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _log_time(ts: str) -> datetime | None:
    """Log timestamps of the platform containers are UTC without a zone."""
    return _parse_time(ts.replace(" ", "T"))


def _since(t0: datetime) -> str:
    return (t0 - timedelta(seconds=2)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _settled(parsed: dict, own: dict[str, dict]) -> tuple[list[str], list[str]]:
    """(pending, failed) among this upload's changed artifacts, judged by Records of the workspace.

    An artifact counts as settled only when Records shows a terminal status saved after the log
    queued it (``_modified`` not earlier than the revision line): a stale status of the previous
    upload, or a namesake's status line in another workspace, cannot settle it.
    """
    pending, failed = [], []
    for ref in parsed["changed"]:
        record = own.get(ref)
        queued = parsed["changed_at"].get(ref)
        modified = _parse_time(record["modified"]) if record else None
        fresh = queued is None or (modified is not None and modified >= queued - timedelta(seconds=CLOCK_SLACK_SECONDS))
        if not record or record["status"] not in TERMINAL or not fresh:
            pending.append(ref)
        elif record["status"] == "DEPLOY_FAILED":
            failed.append(ref)
    return pending, failed


def _unsettled_own(own: dict[str, dict]) -> list[str]:
    """Artifacts of the app that are not in a terminal status (DRAFT, DEPS_WAITING, ...)."""
    return sorted(ref for ref, record in own.items() if record["status"] not in TERMINAL)


def wait_by_log(command: list[str], source_key: str, app_id: str, wait_seconds: float,
                started_at: float, records_status, expect_revisions: bool | None = None) -> dict | None:
    """Poll the log and Records until this upload settled. None if the log broke.

    ``records_status()`` returns {ref: {"status", "modified"}} of this app's own artifacts in the
    workspace. The upload is finished when the log shows it was handled (unchanged, started,
    import error) AND every artifact it queued is settled (see ``_settled``) AND no artifact of
    the app is still in a non-terminal status.
    """
    failed_seen_at = None
    quiet_since = None
    while True:
        lines = read_log(command)
        if lines is None:
            return None
        parsed = parse_upload_log(lines, source_key, app_id)
        own = records_status()
        # Re-queued refs without a revision line may be another app's of the same watcher pass.
        parsed["changed"] = [ref for ref in parsed["changed"] if ref in parsed["own_changed"] or ref in own]
        now = time.monotonic()
        elapsed = now - started_at
        if parsed["import_errors"]:
            return {**parsed, "pending": [], "finished": True, "own": own}
        pending, failed = _settled(parsed, own) if parsed["started"] else ([], [])
        unsettled = _unsettled_own(own)
        handled = parsed["started"] or parsed["unchanged"]
        if handled and not pending and not unsettled:
            if parsed["changed"]:
                retried = all(parsed["failed_count"].get(ref, 0) >= 2 for ref in failed)
                failed_seen_at = failed_seen_at or now
                if not failed or retried or now - failed_seen_at >= FAILED_RETRY_WAIT_SECONDS:
                    return {**parsed, "pending": [], "finished": True, "own": own}
            elif parsed["unchanged"] and not parsed["started"]:
                return {**parsed, "pending": [], "finished": True, "own": own}
            elif not expect_revisions:
                # Started, nothing queued so far. "Start artifacts uploading" is logged before the
                # artifacts are read, so quiet alone proves nothing when artifact files changed
                # (expect_revisions): then the wait goes on until revisions appear or the limit.
                quiet_since = quiet_since or now
                if now - quiet_since >= NO_CHANGES_QUIET_SECONDS:
                    return {**parsed, "pending": [], "finished": True, "own": own}
        else:
            quiet_since = None
        if elapsed >= wait_seconds:
            if not handled:
                left = ["<upload not picked up>"]
            elif expect_revisions and not parsed["changed"]:
                left = ["<artifact files changed, but no revision seen yet>"]
            else:
                left = sorted(set(pending) | set(unsettled)) or ["<no terminal status confirmed>"]
            return {**parsed, "pending": left, "finished": False, "own": own}
        _sleep(POLL_SECONDS)


# ---------------------------------------------------------------- git

def _git_inside(git: str, app_dir: str) -> bool:
    inside = subprocess.run([git, "-C", app_dir, "rev-parse", "--is-inside-work-tree"],
                            capture_output=True, text=True, timeout=15)
    return inside.returncode == 0 and inside.stdout.strip() == "true"


CONFIRMED_TAG = "[confirmed]"
UNCONFIRMED_TAG = "[unconfirmed]"


def git_deploy_state(app_dir: str, app_id: str) -> dict | None:
    """What git knows before this upload, relative to the last CONFIRMED deploy of this app.

    Every deploy commits the directory with `[confirmed]` (this upload's processing was seen to the
    end) or `[unconfirmed]`. `artifacts_changed` compares the files under artifacts/ with the last
    confirmed deploy commit — not with HEAD, which may be a timed-out deploy or a manual commit — and
    is True when there is no confirmed deploy yet. None when the directory is not under git.
    """
    git = shutil.which("git")
    if not git:
        return None
    try:
        if not _git_inside(git, app_dir):
            return None
        log = subprocess.run([git, "-C", app_dir, "log", "--format=%H %s", "--fixed-strings",
                              f"--grep=deploy {app_id} "], capture_output=True, text=True, timeout=15)
        confirmed = None
        for line in log.stdout.splitlines():
            commit, _, subject = line.partition(" ")
            if subject.startswith(f"deploy {app_id} ") and subject.endswith(CONFIRMED_TAG):
                confirmed = commit
                break
        if confirmed is None:
            return {"artifacts_changed": True, "confirmed_commit": None}
        diff = subprocess.run([git, "-C", app_dir, "diff", "--quiet", confirmed, "--", "artifacts"],
                              capture_output=True, text=True, timeout=30)
        untracked = subprocess.run([git, "-C", app_dir, "ls-files", "--others", "--exclude-standard", "--",
                                    "artifacts"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    changed = diff.returncode != 0 or bool(untracked.stdout.strip())
    return {"artifacts_changed": changed, "confirmed_commit": confirmed[:10]}


def commit_app_dir(app_dir: str, message: str) -> dict | None:
    """Commit the application directory after a deploy, even without file changes.

    One commit per deploy, so the agent's journal can name the deploy it refers to.
    """
    git = shutil.which("git")
    if not git:
        return None
    try:
        if not _git_inside(git, app_dir):
            return None
        subprocess.run([git, "-C", app_dir, "add", "-A", "--", "."], capture_output=True, text=True,
                       timeout=30, check=True)
        staged = subprocess.run([git, "-C", app_dir, "diff", "--cached", "--quiet", "--", "."],
                                capture_output=True, text=True, timeout=30)
        files_changed = staged.returncode != 0
        # The directory may sit inside a bigger repository: a deploy commit must not carry what the
        # user staged elsewhere in it.
        # --no-relative: `diff.relative=true` would hide every path outside the directory;
        # --no-renames: a rename from outside into the directory must show its source path too.
        listing = [git, "-C", app_dir, "diff", "--cached", "--name-only", "--no-relative", "--no-renames"]
        everything = subprocess.run(listing, capture_output=True, text=True, timeout=30, check=True)
        own = subprocess.run(listing + ["--", "."], capture_output=True, text=True, timeout=30, check=True)
        foreign = sorted(set(everything.stdout.splitlines()) - set(own.stdout.splitlines()))
        if foreign:
            return {"error": "No deploy commit: the repository has staged changes outside the application "
                             f"directory ({', '.join(foreign[:5])}). Commit or unstage them."}
        done = subprocess.run([git, "-C", app_dir, "commit", "-q", "--allow-empty", "-m", message],
                              capture_output=True, text=True, timeout=30)
        if done.returncode != 0:
            return {"error": (done.stderr or done.stdout).strip()[:500]}
        head = subprocess.run([git, "-C", app_dir, "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=15)
        return {"hash": head.stdout.strip() or None, "files_changed": files_changed}
    except (OSError, subprocess.SubprocessError) as e:
        return {"error": str(e)[:500]}


# ---------------------------------------------------------------- entry point

def _refuse_scope_problems(app_dir: str, ws_ids: set[str]) -> None:
    problems = check_artifact_scope(app_dir, ws_ids)
    if problems:
        raise DeployError("Refused, the application reaches outside its workspace:\n- " + "\n- ".join(problems))


_PATCH_NOTE = ("DEPLOYED means the patch is registered; it is applied separately. "
               "Check the records or artifacts the patch creates.")


def deploy(app_dir: str, workspace: str | None = None, members: list[str] | None = None,
           wait_seconds: float = DEFAULT_WAIT_SECONDS, profile=None, config_dir=None) -> dict:
    started_at = time.monotonic()
    app_dir = os.path.abspath(os.path.expanduser(app_dir or ""))
    if not os.path.isdir(app_dir):
        raise DeployError(f"Application directory not found: {app_dir}")
    meta = read_meta(app_dir)
    app_id = meta["id"]
    ws, configured = resolve_workspace(workspace)
    # The system id may differ from the id (it is the prefix of ids in the workspace): resolve it
    # first for an existing workspace, so refs written with it are not refused.
    known_sys = workspace_system_id(ws, profile, config_dir) \
        if _exists(f"emodel/workspace@{ws}", profile, config_dir) else ws
    _refuse_scope_problems(app_dir, {ws, known_sys})
    check_app_id_free_globally(app_id, profile, config_dir)
    created = ensure_workspace(ws, app_id, meta.get("name"), configured, profile, config_dir)
    ws_sys = workspace_system_id(ws, profile, config_dir) if created else known_sys
    guards.remember_generation_workspace(ws, ws_sys)
    added = ensure_members(ws, list(members or []), profile, config_dir)

    zip_bytes = build_zip(app_dir)
    git_state = git_deploy_state(app_dir, app_id)
    expect_revisions = git_state["artifacts_changed"] if git_state else None
    t0 = _now()
    stamp = t0.strftime("%Y-%m-%dT%H:%M:%SZ")
    command = log_command(_since(t0))
    result = {"app": app_id, "workspace": ws, "workspace_system_id": ws_sys,
              "workspace_created": created, "members_added": added, "deploy_time": stamp}
    try:
        app_record = upload(zip_bytes, ws, profile, config_dir)
    except UploadRejected as e:
        commit = commit_app_dir(app_dir, f"deploy {app_id} {stamp}: upload rejected {UNCONFIRMED_TAG}")
        hint = "The platform refused the whole archive; nothing was deployed. Fix the cause and redeploy."
        if "access denied" in str(e).lower():
            hint = (f"The profile '{profile}' may not upload applications; deploy needs an administrator. "
                    "Do not switch the active profile for deploys: the operator sets CITECK_DEPLOY_PROFILE.")
        return {**result, "ok": False, "outcome": "upload_rejected", "error": str(e), "commit": commit,
                "hint": hint,
                "elapsed_seconds": round(time.monotonic() - started_at, 1)}
    result["app_record"] = app_record
    source_key = app_record.split("@", 1)[1] if "@" in app_record else f"{ws_sys}:{app_id}"
    if source_key.startswith("DELETED_"):
        result["warning"] = ("ecos-apps answered with a stale workspace cache (DELETED_ prefix); the app is "
                             "stored in the workspace and processed under that source key.")

    def records_status() -> dict[str, dict]:
        return {a["artifact"]: a for a in query_artifacts(app_id, ws, ws_sys, profile, config_dir)}

    waited = wait_by_log(command, source_key, app_id, wait_seconds, started_at, records_status,
                         expect_revisions) if command is not None else None
    if waited is None:
        current = {ref: record["status"] for ref, record in records_status().items()}
        failed_now = sorted(ref for ref, status in current.items() if status == "DEPLOY_FAILED")
        commit = commit_app_dir(app_dir, f"deploy {app_id} {stamp}: unconfirmed {UNCONFIRMED_TAG}")
        return {**result, "ok": False, "outcome": "unconfirmed", "completion": "none",
                "artifacts_total": len(current), "failed_artifacts": failed_now, "commit": commit,
                "hint": "The ecos-apps log is not available, so the end of this upload and the error texts "
                        "cannot be confirmed. Statuses in Records may still be from the previous upload.",
                "elapsed_seconds": round(time.monotonic() - started_at, 1)}
    result["completion"] = "log"

    current = {ref: record["status"] for ref, record in waited["own"].items()}
    changed = []
    for ref in waited["changed"]:
        status = current.get(ref) or waited["status"].get(ref) or "UNKNOWN"
        item = {"artifact": ref, "status": status if ref not in waited["pending"] else "PENDING"}
        if status == "DEPLOY_FAILED" and ref not in waited["pending"]:
            item["errors"] = waited["errors"].get(ref) or ["Error text not available."]
        if ref.startswith("app/patch$"):
            item["note"] = _PATCH_NOTE
        changed.append(item)
    failed_now = sorted(ref for ref, status in current.items() if status == "DEPLOY_FAILED")
    failed_changed = [c for c in changed if c["status"] == "DEPLOY_FAILED"]
    pending = waited["pending"]
    if waited["import_errors"]:
        outcome = "import_failed"
        result["import_errors"] = waited["import_errors"]
    elif not waited["finished"]:
        outcome = "timeout"
    elif waited["unchanged"] and not changed:
        outcome = "unchanged"
    elif not changed:
        outcome = "no_artifact_changes"
    elif failed_changed:
        outcome = "deployed_with_errors"
    else:
        outcome = "deployed"
    # Confirmed: this upload's processing was seen to the end, or nothing had to be processed because
    # the files equal the last confirmed deploy (git). Any other end keeps the chain unconfirmed.
    processed = waited["finished"] and not pending and not waited["import_errors"]
    if outcome in ("unchanged", "no_artifact_changes"):
        confirmed = processed and expect_revisions is False
    else:
        confirmed = processed
    ok = confirmed and not failed_now
    if outcome in ("unchanged", "no_artifact_changes") and not confirmed:
        result["hint"] = ("Nothing was processed by this upload, and the files differ from the last confirmed "
                          "deploy (or there is none, or the directory is not under git): the statuses on the "
                          "stand are not confirmed for these files. Change an artifact and deploy again, or "
                          "wait a minute if a previous deploy may still be running.")
    summary = f"{outcome}, {len(changed)} changed, {len(failed_changed)} failed"
    tag = CONFIRMED_TAG if confirmed else UNCONFIRMED_TAG
    commit = commit_app_dir(app_dir, f"deploy {app_id} {stamp}: {summary} {tag}")
    if pending:
        result["pending_statuses"] = {ref: current.get(ref) for ref in pending if ref in current}
    result.update({
        "ok": ok, "outcome": outcome, "changed": changed, "pending": pending,
        "artifacts_total": len(current), "failed_artifacts": failed_now,
        "commit": commit, "elapsed_seconds": round(time.monotonic() - started_at, 1),
    })
    if outcome == "no_artifact_changes" and confirmed:
        result["hint"] = ("The platform processed the upload but no artifact changed. If you changed an "
                          "artifact, check its directory and id." + (
                              " The directory is not under git, so the tool cannot tell whether an artifact "
                              "should have changed: the result is not confirmed." if expect_revisions is None else ""))
    earlier = sorted(set(failed_now) - {c["artifact"] for c in failed_changed})
    if earlier:
        result["hint"] = "Artifacts not changed by this upload are still failed from an earlier upload."
        history = log_command((_now() - timedelta(minutes=EARLIER_ERRORS_MINUTES)).strftime("%Y-%m-%dT%H:%M:%SZ"))
        lines = read_log(history) if history else None
        if lines:
            result["earlier_errors"] = last_errors(lines, earlier)
    return result
