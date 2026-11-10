"""Run-time guards for agent sessions that generate applications.

Both guards are conveniences for a disposable stand, not a security boundary: an agent with
admin rights can bypass them with another HTTP client. They keep an honest agent on the
intended path and make a bypass visible.

- ``CITECK_ALLOWED_SERVERS``: comma-separated base URLs. When set, every Records API call to a
  profile on another server is refused before any credentials are read.
- ``CITECK_GENERATION_MODE``: when truthy, ``records_mutate`` refuses records of artifact
  sources (types, forms, journals, processes, permissions, menus, applications, workspaces):
  artifacts reach the stand only through ``deploy_app``. With ``CITECK_GEN_WORKSPACE`` set it
  also refuses records that name another workspace (in the record id, ``_workspace`` or
  ``_parent``).
"""
import os

ALLOWED_SERVERS_ENV = "CITECK_ALLOWED_SERVERS"
GENERATION_MODE_ENV = "CITECK_GENERATION_MODE"
GEN_WORKSPACE_ENV = "CITECK_GEN_WORKSPACE"

# Records sources that hold platform artifacts (source id without the app prefix is matched too).
ARTIFACT_SOURCES = frozenset({
    "emodel/type", "emodel/types-repo", "emodel/perms", "emodel/permissions", "emodel/type-perms",
    "emodel/permission-settings", "emodel/permission-settings-repo",
    "emodel/num-template", "emodel/aspect", "emodel/workspace", "emodel/working-schedule",
    "emodel/secret", "emodel/endpoint",
    # Groups are global: an app must not create or change them.
    "emodel/authority-group",
    "uiserv/form", "uiserv/journal", "uiserv/action", "uiserv/menu", "uiserv/dashboard",
    "uiserv/board", "uiserv/journal-settings", "uiserv/icon", "uiserv/i18n",
    "eproc/bpmn-def", "eproc/dmn-def", "eproc/bpmn-section", "eproc/cmmn-def",
    "notifications/template", "notifications/notification-template",
    "eapps/ecosapp", "eapps/artifact", "eapps/artifact-patch", "eapps/patch",
    "transformations/template", "integrations/ecos-camel-dsl",
})
_ARTIFACT_LOCAL_SOURCES = frozenset(s.split("/", 1)[1] for s in ARTIFACT_SOURCES)

# Workspace ids (and system ids) learned by deploy_app in this process.
_known_workspaces: set[str] = set()


class GuardError(Exception):
    """A call refused by a run-time guard."""


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _norm_url(url: str) -> str:
    return url.strip().rstrip("/").lower()


def allowed_servers() -> list[str] | None:
    """Allowed base URLs, or None when the allowlist is not configured."""
    raw = os.environ.get(ALLOWED_SERVERS_ENV, "")
    servers = [_norm_url(item) for item in raw.split(",") if item.strip()]
    return servers or None


def check_server_allowed(base_url: str) -> None:
    servers = allowed_servers()
    if servers is not None and _norm_url(base_url) not in servers:
        raise GuardError(
            f"Server {base_url} is not in {ALLOWED_SERVERS_ENV}; calls are allowed only to: "
            + ", ".join(servers))


def generation_mode() -> bool:
    return _truthy(os.environ.get(GENERATION_MODE_ENV))


def remember_generation_workspace(*ids: str) -> None:
    """Record the workspace id and system id deploy_app resolved (they may differ)."""
    _known_workspaces.update(i for i in ids if i)


def _own_workspaces() -> set[str]:
    configured = (os.environ.get(GEN_WORKSPACE_ENV) or "").strip()
    return ({configured} | _known_workspaces) if configured else set()


def _source_of(record_id: str) -> str:
    """Source part of a record id: 'emodel/type@x' -> 'emodel/type', 'type@x' -> 'type'."""
    return record_id.split("@", 1)[0].strip().lower()


def is_artifact_source(record_id: str) -> bool:
    source = _source_of(record_id)
    return source in ARTIFACT_SOURCES or source in _ARTIFACT_LOCAL_SOURCES


def _named_workspaces(record: dict) -> set[str]:
    """Workspaces a record names: id source 'emodel/<ws>:<type>', id local '<ws>:<id>',
    ``_workspace`` and a ``_parent`` workspace."""
    names = set()
    record_id = str(record.get("id", ""))
    source, _, local = record_id.partition("@")
    source_local = source.split("/", 1)[-1]
    for part in (source_local, local):
        prefix, sep, _ = part.partition(":")
        if sep and prefix:
            names.add(prefix)
    attributes = record.get("attributes") or {}
    for key, value in attributes.items():
        name = key.split("?", 1)[0]
        if name == "_workspace" and value:
            names.add(str(value).split("@", 1)[-1])
        if name == "_parent" and str(value).startswith("emodel/workspace@"):
            names.add(str(value).split("@", 1)[1])
    return names


def check_mutation_allowed(records: list[dict]) -> None:
    """Refuse direct writes to artifact sources and to other workspaces in generation mode."""
    if not generation_mode():
        return
    refused = sorted({str(r.get("id", "")) for r in records if is_artifact_source(str(r.get("id", "")))})
    if refused:
        raise GuardError(
            "Generation mode: artifacts are written only by deploy_app, records_mutate refuses "
            f"artifact sources: {', '.join(refused)}. Change the artifact file in the application "
            "directory and run deploy_app. Data records of your own types are allowed.")
    own = _own_workspaces()
    if not own:
        return
    foreign = sorted({ws for r in records for ws in _named_workspaces(r)} - own)
    if foreign:
        raise GuardError(
            f"Generation mode: records of other workspaces ({', '.join(foreign)}) are refused; "
            f"work only in {', '.join(sorted(own))}.")
