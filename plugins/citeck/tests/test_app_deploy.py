"""deploy_app: scope checks, workspace, archive, log parsing, waiting and commit."""

import io
import itertools
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from unittest.mock import patch

import pytest
from fastmcp import Client

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib import app_deploy, guards
from lib.config import save_credentials
from lib.records_api import ServerError
from servers.citeck_mcp import mcp

WS = "gen-ws"
APP = "gen-app"
SRC = f"{WS}:{APP}"


def _line(ts, msg, trace="t-up", level="INFO", thread="rtifactsWatcher"):
    return f"\x1b[2m2026-11-10 {ts}\x1b[0;39m {level} [{thread}] [{trace}] [system] r.c.e.a.Logger : {msg}"


UPLOAD = _line("09:34:32.550", f"Upload application '{APP}'", trace="t-req", thread="io-exec-4")
UPLOAD_CHANGED = [UPLOAD, _line("09:34:32.578", f"Application content changed. App ID: '{APP}' New content id: 1",
                                trace="t-req")]
UNCHANGED = [UPLOAD, _line("09:34:32.578", f"Application content doesn't change. App ID: '{APP}'", trace="t-req")]


def _start(src=SRC, ts="09:34:36.368", trace="t-up"):
    return _line(ts, "Start artifacts uploading from source AppSourceKey(appName=eapps, "
                     f"source=SourceKey(id={src}, type=ECOS_APP)). New date: x", trace=trace)


START = _start()


def _revision(ts, ref, src=SRC, trace="t-up"):
    return _line(ts, f'Create new artifact revision entity {{"ru":"Имя (1)"}}({ref}). Source: '
                     f"SourceKey(id={src}, type=ECOS_APP)", trace=trace)


def _status(ts, ref, old, new, trace="t-up"):
    return _line(ts, f"Deploy status changed for {ref} from {old} to {new}", trace=trace)


def _failed(ts, ref, message, trace="t-up"):
    return [_line(ts, f"Artifact deploy failed: {ref}. Errors: ", trace=trace, level="ERROR"),
            json.dumps({"type": "SAXParseException", "message": message, "stackTrace": ["a"]})]


def _deployed(ref, ts="09:34:37"):
    return [_revision(f"{ts}.1", ref), _status(f"{ts}.2", ref, "DRAFT", "DEPLOYED")]


@pytest.fixture
async def client():
    async with Client(mcp) as c:
        yield c


@pytest.fixture
def app_dir(tmp_path):
    root = tmp_path / "app"
    (root / "artifacts/model/type").mkdir(parents=True)
    (root / "artifacts/ui/journal").mkdir(parents=True)
    (root / "meta.json").write_text(json.dumps({"id": APP, "name": {"ru": "Пробное"}, "version": "1.0"}))
    (root / "artifacts/model/type/deal.yml").write_text("id: deal\nparentRef: emodel/type@data-list\n")
    (root / "artifacts/ui/journal/deals.yml").write_text("id: deals\ntypeRef: emodel/type@CURRENT_WS:deal\n")
    return root


@pytest.fixture(autouse=True)
def no_env(monkeypatch):
    monkeypatch.delenv(app_deploy.GEN_WORKSPACE_ENV, raising=False)
    monkeypatch.delenv(app_deploy.EAPPS_LOG_CMD_ENV, raising=False)
    guards._known_workspaces.clear()


class Stand:
    """In-memory replacement of the Records calls made by app_deploy."""

    def __init__(self, workspace_exists=True, ws_apps=(), global_apps=(), artifacts=None, upload_error=None,
                 sys_id=WS, app_record=None):
        self.workspace_exists = workspace_exists
        self.ws_apps = list(ws_apps)
        self.global_apps = set(global_apps)
        self.artifacts = artifacts if artifacts is not None else []
        self.upload_error = upload_error
        self.sys_id = sys_id
        self.app_record = app_record or f"eapps/ecosapp@{sys_id}:{APP}"
        self.mutations = []
        self.members = [{"authorities": ["emodel/person@admin"], "memberRole": "MANAGER"}]

    def load(self, ids, attributes, **_):
        # Like the stand: `id` echoes the local id even for a missing record.
        ref = ids[0]
        if "m" in attributes:
            return {"records": [{"attributes": {"m": self.members}}]}
        if "sys" in attributes:
            return {"records": [{"attributes": {"sys": self.sys_id}}]}
        local = ref.split("@", 1)[1]
        found = local in self.global_apps if ref.startswith("eapps/ecosapp@") else self.workspace_exists
        attrs = {"id": local, "missing": None if found else True}
        return {"records": [{"attributes": {k: v for k, v in attrs.items() if k in attributes}}]}

    def query(self, source_id, **kwargs):
        if source_id == "eapps/ecosapp":
            return {"records": [{"attributes": {"id": a}} for a in self.ws_apps]}
        return {"records": [{"id": "eapps/artifact@x",
                             "attributes": {"id": a["ref"].replace("$", "$" + self.sys_id + ":"),
                                            "status": a["status"],
                                            # Saved after the log lines of these tests unless a test says otherwise.
                                            "modified": a.get("modified", "2026-11-10T23:00:00Z")}}
                            for a in self.artifacts]}

    def mutate(self, records, **_):
        self.mutations.append(records)
        if records[0]["id"] == "eapps/ecosapp@" and self.upload_error:
            body = {"messages": [{"level": "ERROR", "msg": {"msg": self.upload_error}}]}
            raise ServerError("HTTP 500", status_code=500, response_body=json.dumps(body))
        return {"records": [{"id": self.app_record}], "messages": []}


@pytest.fixture
def stand():
    holder = {}

    def install(**kwargs):
        holder["s"] = Stand(**kwargs)
        return holder["s"]

    clock = itertools.count(0, 1)
    with patch("lib.app_deploy.records_api.records_load", side_effect=lambda *a, **k: holder["s"].load(*a, **k)), \
         patch("lib.app_deploy.records_api.records_query", side_effect=lambda *a, **k: holder["s"].query(*a, **k)), \
         patch("lib.app_deploy.records_api.records_mutate", side_effect=lambda *a, **k: holder["s"].mutate(*a, **k)), \
         patch("lib.app_deploy._sleep"), \
         patch("lib.app_deploy.time.monotonic", side_effect=lambda: next(clock)):
        yield install


def _with_log(lines):
    return patch.multiple("lib.app_deploy", log_command=lambda since: ["log"],
                          read_log=lambda command: list(lines))


def _art(ref, status, modified=None):
    art = {"ref": ref, "status": status}
    if modified:
        art["modified"] = modified
    return art


# ---------------------------------------------------------------- scope

def test_refuses_other_workspace_when_generation_workspace_set(app_dir, stand, monkeypatch):
    stand()
    monkeypatch.setenv(app_deploy.GEN_WORKSPACE_ENV, WS)
    with pytest.raises(app_deploy.DeployError, match="not the generation workspace"):
        app_deploy.deploy(str(app_dir), workspace="crm-workspace")


def test_refuses_global_default_workspace(app_dir, stand):
    s = stand()
    with pytest.raises(app_deploy.DeployError, match="global entities"):
        app_deploy.deploy(str(app_dir), workspace="default")
    assert s.mutations == []


def test_refuses_installed_global_app_id(app_dir, stand):
    s = stand(global_apps={APP})
    with pytest.raises(app_deploy.DeployError, match="installed on the stand"):
        app_deploy.deploy(str(app_dir), workspace=WS)
    assert s.mutations == []


def test_refuses_workspace_artifact(app_dir, stand):
    stand()
    (app_dir / "artifacts/model/workspace").mkdir(parents=True)
    (app_dir / "artifacts/model/workspace/other.yml").write_text("id: other\n")
    with pytest.raises(app_deploy.DeployError, match="must not create workspaces"):
        app_deploy.deploy(str(app_dir), workspace=WS)


@pytest.mark.parametrize("content, refused", [
    ("id: p\ntypeRef: emodel/type@crm-deal\n", True),
    ("id: p\ntypeRef: emodel/type@crm-workspace:crm-deal\n", True),
    ("id: p\ntypeRef: >-\n  emodel/type@crm-deal\n", True),
    ('{"id": "p", "typeRef": "emodel/type@crm-deal"}', True),
    ("id: p\ntypeRef: emodel/type@CURRENT_WS:deal\n", False),
])
def test_permissions_must_name_types_of_the_workspace(app_dir, content, refused):
    (app_dir / "artifacts/model/permissions").mkdir(parents=True)
    (app_dir / "artifacts/model/permissions/deal-perms.yml").write_text(content)
    assert bool(app_deploy.check_artifact_scope(str(app_dir), {WS})) is refused


def test_permission_settings_are_checked_too(app_dir):
    (app_dir / "artifacts/model/permission-settings").mkdir(parents=True)
    (app_dir / "artifacts/model/permission-settings/s.yml").write_text("id: s\ntypeRef: emodel/type@crm-deal\n")
    assert app_deploy.check_artifact_scope(str(app_dir), {WS})


@pytest.mark.parametrize("content, refused", [
    ("id: p\ntarget: ui/menu$admin-workspace-menu\ntype: json\n", True),
    ("id: p\ntarget: ui/menu$admin-workspace-menu\nworkspace: admin$workspace\n", True),
    ("id: p\ntarget: ui/menu$menu\nworkspace: other-ws\n", True),
    (f"id: p\ntarget: ui/menu$menu\nworkspace: {WS}\n", False),
])
def test_artifact_patch_must_apply_in_the_workspace(app_dir, content, refused):
    (app_dir / "artifacts/app/artifact-patch").mkdir(parents=True)
    (app_dir / "artifacts/app/artifact-patch/p.yml").write_text(content)
    assert bool(app_deploy.check_artifact_scope(str(app_dir), {WS})) is refused


@pytest.mark.parametrize("content, refused", [
    ("type: mutate\nrecords:\n  - id: emodel/type@crm-deal\n", True),
    ("type: mutate\nrecords:\n  - id: emodel/other-ws:stage@x\n", True),
    ("type: mutate\nrecords:\n  - id: uiserv/form@CURRENT_WS:deal-form\n", False),
    (f"type: mutate\nrecords:\n  - id: emodel/{WS}:stage@\n    attributes: {{name: x}}\n", False),
    ("type: mutate\nrecords:\n  - id: emodel/person@fet\n", False),
    ("type: mutate\nrecords:\n  - id: emodel/workspace-member@\n    attributes: {_parent: emodel/workspace@other-ws}\n",
     True),
    (f"type: mutate\nrecords:\n  - id: emodel/workspace-member@\n    attributes: {{_parent: emodel/workspace@{WS}}}\n",
     False),
    ("type: mutate\nrecords:\n  - id: emodel/workspace@other-ws\n    attributes: {name: x}\n", True),
    (f"type: mutate\nrecords:\n  - id: emodel/{WS}:deal@\n    attributes: {{_parent: emodel/{WS}:deal@1}}\n", False),
])
def test_patch_may_touch_only_the_workspace(app_dir, content, refused):
    (app_dir / "artifacts/app/patch").mkdir(parents=True)
    (app_dir / "artifacts/app/patch/p.yml").write_text(content)
    assert bool(app_deploy.check_artifact_scope(str(app_dir), {WS})) is refused


def test_refuses_missing_meta(tmp_path, stand):
    stand()
    (tmp_path / "artifacts").mkdir()
    with pytest.raises(app_deploy.DeployError, match="No meta.json"):
        app_deploy.deploy(str(tmp_path), workspace=WS)


@pytest.mark.parametrize("app_id", ["", "ws:app", "App", "a", "x" * 70])
def test_refuses_bad_app_id(app_dir, stand, app_id):
    stand()
    (app_dir / "meta.json").write_text(json.dumps({"id": app_id}))
    with pytest.raises(app_deploy.DeployError, match="must match"):
        app_deploy.deploy(str(app_dir), workspace=WS)


def test_refuses_missing_workspace_argument(app_dir, stand):
    stand()
    with pytest.raises(app_deploy.DeployError, match="target workspace"):
        app_deploy.deploy(str(app_dir))


# ---------------------------------------------------------------- workspace and members

def test_creates_missing_workspace_before_upload(app_dir, stand):
    s = stand(workspace_exists=False, artifacts=[_art("model/type$deal", "DEPLOYED")])
    with _with_log(UPLOAD_CHANGED + [START, *_deployed("model/type$deal")]):
        result = app_deploy.deploy(str(app_dir), workspace=WS)
    assert result["workspace_created"] is True and result["ok"] is True
    ids = [records[0]["id"] for records in s.mutations]
    assert ids[0] == "emodel/workspace@" and ids[-1] == "eapps/ecosapp@"
    assert s.mutations[0][0]["attributes"]["visibility"] == "PRIVATE"


def test_refuses_existing_workspace_with_foreign_apps(app_dir, stand):
    s = stand(ws_apps=["someone-else"])
    with pytest.raises(app_deploy.DeployError, match="already holds other applications"):
        app_deploy.deploy(str(app_dir), workspace=WS)
    assert s.mutations == []


def test_configured_workspace_skips_foreign_app_check(app_dir, stand, monkeypatch):
    stand(ws_apps=["someone-else"], artifacts=[_art("model/type$deal", "DEPLOYED")])
    monkeypatch.setenv(app_deploy.GEN_WORKSPACE_ENV, WS)
    with _with_log(UPLOAD_CHANGED + [START, *_deployed("model/type$deal")]):
        assert app_deploy.deploy(str(app_dir))["workspace"] == WS


def test_adds_missing_members_only(app_dir, stand):
    s = stand(artifacts=[_art("model/type$deal", "DEPLOYED")])
    with _with_log(UPLOAD_CHANGED + [START, *_deployed("model/type$deal")]):
        result = app_deploy.deploy(str(app_dir), workspace=WS, members=["admin", "fet"])
    assert result["members_added"] == ["fet"]
    member = [r[0] for r in s.mutations if r[0]["id"] == "emodel/workspace-member@"][0]
    assert member["attributes"]["_parent"] == f"emodel/workspace@{WS}"
    assert member["attributes"]["memberRole"] == "USER"


def test_workspace_system_id_is_used_for_source_key_and_refs(app_dir, stand):
    stand(sys_id="gen_ws", artifacts=[_art("model/type$deal", "DEPLOYED")])
    with _with_log(UPLOAD_CHANGED + [_start(src=f"gen_ws:{APP}"),
                                     _revision("09:34:37.1", "model/type$deal", src=f"gen_ws:{APP}"),
                                     _status("09:34:37.2", "model/type$deal", "DRAFT", "DEPLOYED")]):
        result = app_deploy.deploy(str(app_dir), workspace=WS)
    assert result["workspace_system_id"] == "gen_ws"
    assert result["ok"] is True and result["changed"] == [{"artifact": "model/type$deal", "status": "DEPLOYED"}]
    assert guards._known_workspaces == {WS, "gen_ws"}


def test_stale_workspace_answer_is_tracked_under_its_source_key(app_dir, stand):
    stale = f"DELETED_{WS}:{APP}"
    stand(app_record=f"eapps/ecosapp@{stale}", artifacts=[_art("model/type$deal", "DEPLOYED")])
    with _with_log(UPLOAD_CHANGED + [_start(src=stale), _revision("09:34:37.1", "model/type$deal", src=stale),
                                     _status("09:34:37.2", "model/type$deal", "DRAFT", "DEPLOYED")]):
        result = app_deploy.deploy(str(app_dir), workspace=WS)
    assert result["ok"] is True and "stale workspace cache" in result["warning"]


# ---------------------------------------------------------------- archive

def test_zip_skips_git_and_hidden_files(app_dir):
    (app_dir / "artifacts/.git").mkdir()
    (app_dir / "artifacts/.git/HEAD").write_text("x")
    (app_dir / "artifacts/ui/journal/.DS_Store").write_text("x")
    (app_dir / "LOOP-JOURNAL.md").write_text("x")
    names = zipfile.ZipFile(io.BytesIO(app_deploy.build_zip(str(app_dir)))).namelist()
    assert names == ["meta.json", "artifacts/model/type/deal.yml", "artifacts/ui/journal/deals.yml"]


def test_zip_is_stable(app_dir):
    assert app_deploy.build_zip(str(app_dir)) == app_deploy.build_zip(str(app_dir))


def test_upload_sends_workspace_and_base64_content(app_dir, stand):
    s = stand(artifacts=[_art("model/type$deal", "DEPLOYED")])
    with _with_log(UPLOAD_CHANGED + [START, *_deployed("model/type$deal")]):
        app_deploy.deploy(str(app_dir), workspace=WS)
    attrs = s.mutations[-1][0]["attributes"]
    assert attrs["_workspace"] == WS
    assert attrs["_content"][0]["url"].startswith("data:application/zip;base64,")


def test_upload_rejected_by_platform_returns_text(app_dir, stand):
    stand(upload_error="You can't upload application 'gen-app' with artifacts which is belong to other ECOS applications")
    with _with_log(UPLOAD_CHANGED):
        result = app_deploy.deploy(str(app_dir), workspace=WS)
    assert result["ok"] is False and result["outcome"] == "upload_rejected"
    assert "belong to other ECOS applications" in result["error"]


# ---------------------------------------------------------------- log parsing

def test_parse_changed_artifacts_of_own_upload_only():
    lines = UPLOAD_CHANGED + [
        _revision("09:34:30.0", "ui/form$early"),  # before the start line of this upload
        START,
        _revision("09:34:37.1", "ui/journal$deals"),
        _revision("09:34:37.2", "ui/form$foreign", src="other-ws:other-app"),
        _revision("09:34:37.3", "ui/form$other-trace", trace="t-other"),
        _status("09:34:37.4", "ui/journal$deals", "DEPLOYED", "DRAFT"),
        _status("09:34:37.5", "ui/journal$deals", "DRAFT", "DEPLOYED", trace="t-deploy"),
        _status("09:34:37.6", "ui/form$foreign", "DRAFT", "DEPLOYED"),
    ]
    parsed = app_deploy.parse_upload_log(lines, SRC, APP)
    assert parsed["started"] is True and parsed["unchanged"] is False
    assert parsed["changed"] == ["ui/journal$deals"]
    assert parsed["status"]["ui/journal$deals"] == "DEPLOYED"


def test_parse_latest_state_wins_after_platform_retry():
    lines = [START, _revision("09:34:37.1", "process/bpmn$p"),
             _status("09:34:38.1", "process/bpmn$p", "DRAFT", "DEPLOY_FAILED"),
             _status("09:35:00.0", "process/bpmn$p", "DEPLOY_FAILED", "DRAFT", trace="t-r")]
    parsed = app_deploy.parse_upload_log(lines, SRC, APP)
    assert parsed["status"]["process/bpmn$p"] == "DRAFT" and parsed["failed_count"]["process/bpmn$p"] == 1


def test_parse_requeued_artifact_without_revision_counts_as_changed():
    lines = [START, _status("09:34:37.1", "process/bpmn$p", "DEPLOY_FAILED", "DRAFT"),
             _status("09:34:38.1", "process/bpmn$p", "DRAFT", "DEPLOYED", trace="t-x")]
    parsed = app_deploy.parse_upload_log(lines, SRC, APP)
    assert parsed["changed"] == ["process/bpmn$p"] and parsed["status"]["process/bpmn$p"] == "DEPLOYED"


def test_parse_error_text_from_json_line_and_empty_text():
    lines = [START, _revision("09:34:37.1", "process/bpmn$p"), _revision("09:34:37.2", "model/num-template$n"),
             *_failed("09:34:38.0", "process/bpmn$p", "cvc-complex-type.4: targetNamespace"),
             _status("09:34:38.1", "process/bpmn$p", "DRAFT", "DEPLOY_FAILED"),
             _line("09:34:38.2", "Artifact deploy failed: model/num-template$n. Errors: ", level="ERROR"),
             _status("09:34:38.3", "model/num-template$n", "DRAFT", "DEPLOY_FAILED")]
    parsed = app_deploy.parse_upload_log(lines, SRC, APP)
    assert parsed["errors"]["process/bpmn$p"] == ["cvc-complex-type.4: targetNamespace"]
    assert parsed["errors"]["model/num-template$n"] == ["The platform logged no error text."]


def test_parse_unchanged_only_in_own_upload_request():
    assert app_deploy.parse_upload_log(UNCHANGED, SRC, APP)["unchanged"] is True
    lone = [_line("09:34:32.578", f"Application content doesn't change. App ID: '{APP}'", trace="t-x")]
    assert app_deploy.parse_upload_log(lone, SRC, APP)["unchanged"] is False


def test_parse_import_errors_of_own_source():
    lines = [START,
             _line("09:34:36.5", "Artifact uploading failed. Source: AppSourceKey(appName=eapps, "
                                 f"source=SourceKey(id={SRC}, type=ECOS_APP)) Type: ui/form Artifact: x",
                   level="ERROR"),
             "java.lang.IllegalStateException: Form id is empty", "\tat a.b.C(C.kt:1)",
             _line("09:34:36.6", "Artifacts can't be received from source: AppSourceKey(appName=eapps, "
                                 "source=SourceKey(id=other:app, type=ECOS_APP))", level="ERROR")]
    errors = app_deploy.parse_upload_log(lines, SRC, APP)["import_errors"]
    assert len(errors) == 1 and "Form id is empty" in errors[0] and "ui/form" in errors[0]


# ---------------------------------------------------------------- waiting

def test_all_changed_deployed(app_dir, stand):
    stand(artifacts=[_art("model/type$deal", "DEPLOYED"), _art("ui/journal$deals", "DEPLOYED")])
    with _with_log(UPLOAD_CHANGED + [START, *_deployed("ui/journal$deals")]):
        result = app_deploy.deploy(str(app_dir), workspace=WS)
    assert result["ok"] is True and result["outcome"] == "deployed" and result["completion"] == "log"
    assert result["changed"] == [{"artifact": "ui/journal$deals", "status": "DEPLOYED"}]
    assert result["artifacts_total"] == 2


def test_namesake_in_other_workspace_does_not_finish_the_wait(app_dir, stand):
    # The log line has no workspace: it may be a namesake's. Records of this workspace still say DRAFT.
    stand(artifacts=[_art("ui/form$f", "DRAFT")])
    with _with_log(UPLOAD_CHANGED + [START, _revision("09:34:37.1", "ui/form$f"),
                                     _status("09:34:37.2", "ui/form$f", "DRAFT", "DEPLOYED", trace="t-other")]):
        result = app_deploy.deploy(str(app_dir), workspace=WS, wait_seconds=60)
    assert result["ok"] is False and result["outcome"] == "timeout"
    assert result["pending"] == ["ui/form$f"] and result["changed"][0]["status"] == "PENDING"


def test_other_app_in_the_same_watcher_pass_is_not_counted(app_dir, stand):
    stand(artifacts=[_art("model/type$deal", "DEPLOYED")])
    with _with_log(UPLOAD_CHANGED + [START, *_deployed("model/type$deal"),
                                     _status("09:34:37.3", "ui/form$someone-elses", "DEPLOYED", "DRAFT")]):
        result = app_deploy.deploy(str(app_dir), workspace=WS)
    assert [c["artifact"] for c in result["changed"]] == ["model/type$deal"] and result["ok"] is True


def test_failed_artifact_reported_with_text_after_platform_retry(app_dir, stand):
    stand(artifacts=[_art("process/bpmn$p", "DEPLOY_FAILED")])
    lines = UPLOAD_CHANGED + [START, _revision("09:34:37.1", "process/bpmn$p"),
                              *_failed("09:34:38.0", "process/bpmn$p", "bad xml"),
                              _status("09:34:38.1", "process/bpmn$p", "DRAFT", "DEPLOY_FAILED"),
                              _status("09:35:00.0", "process/bpmn$p", "DEPLOY_FAILED", "DRAFT", trace="t-r"),
                              *_failed("09:35:01.0", "process/bpmn$p", "bad xml again", trace="t-r"),
                              _status("09:35:01.1", "process/bpmn$p", "DRAFT", "DEPLOY_FAILED", trace="t-r")]
    with _with_log(lines):
        result = app_deploy.deploy(str(app_dir), workspace=WS)
    assert result["ok"] is False and result["outcome"] == "deployed_with_errors"
    assert result["changed"] == [{"artifact": "process/bpmn$p", "status": "DEPLOY_FAILED", "errors": ["bad xml again"]}]


def test_retry_in_progress_at_the_limit_is_not_ok(app_dir, stand):
    # Codex review: a stale DEPLOY_FAILED must not survive a new attempt that is still running.
    stand(artifacts=[_art("process/bpmn$p", "DRAFT")])
    lines = UPLOAD_CHANGED + [START, _revision("09:34:37.1", "process/bpmn$p"),
                              _status("09:34:38.1", "process/bpmn$p", "DRAFT", "DEPLOY_FAILED"),
                              _status("09:35:00.0", "process/bpmn$p", "DEPLOY_FAILED", "DRAFT", trace="t-r")]
    with _with_log(lines):
        result = app_deploy.deploy(str(app_dir), workspace=WS, wait_seconds=60)
    assert result["ok"] is False and result["outcome"] == "timeout" and result["pending"] == ["process/bpmn$p"]


def test_failed_then_retry_succeeds_is_deployed(app_dir, stand):
    stand(artifacts=[_art("ui/form$f", "DEPLOYED")])
    lines = [START, _revision("09:34:37.1", "ui/form$f"),
             _status("09:34:38.1", "ui/form$f", "DRAFT", "DEPLOY_FAILED"),
             _status("09:35:00.1", "ui/form$f", "DEPLOY_FAILED", "DRAFT", trace="t-r"),
             _status("09:35:01.1", "ui/form$f", "DRAFT", "DEPLOYED", trace="t-r")]
    with _with_log(lines):
        result = app_deploy.deploy(str(app_dir), workspace=WS)
    assert result["ok"] is True and result["changed"][0]["status"] == "DEPLOYED"


def test_import_error_is_reported_not_success(app_dir, stand):
    stand(artifacts=[_art("model/type$deal", "DEPLOYED")])
    lines = UPLOAD_CHANGED + [START, _line("09:34:36.5", "Artifacts can't be received from source: "
                                                        f"AppSourceKey(appName=eapps, source=SourceKey(id={SRC}, "
                                                        "type=ECOS_APP))", level="ERROR"),
                              "java.lang.RuntimeException: broken yaml at line 3"]
    with _with_log(lines):
        result = app_deploy.deploy(str(app_dir), workspace=WS)
    assert result["ok"] is False and result["outcome"] == "import_failed"
    assert "broken yaml" in result["import_errors"][0]


def test_started_without_artifact_changes(app_dir, stand):
    stand(artifacts=[_art("model/type$deal", "DEPLOYED")])
    with _with_log(UPLOAD_CHANGED + [START]):
        result = app_deploy.deploy(str(app_dir), workspace=WS)
    # Not under git: the tool cannot tell whether an artifact should have changed.
    assert result["outcome"] == "no_artifact_changes" and result["ok"] is False and "not confirmed" in result["hint"]


def test_upload_not_picked_up_is_timeout(app_dir, stand):
    stand(artifacts=[_art("model/type$deal", "DEPLOYED")])
    with _with_log(UPLOAD_CHANGED):
        result = app_deploy.deploy(str(app_dir), workspace=WS, wait_seconds=60)
    assert result["ok"] is False and result["outcome"] == "timeout"
    assert result["pending"] == ["<upload not picked up>"]


def test_unchanged_upload_returns_at_once_but_without_git_is_not_confirmed(app_dir, stand):
    stand(artifacts=[_art("model/type$deal", "DEPLOYED")])
    with _with_log(UNCHANGED):
        result = app_deploy.deploy(str(app_dir), workspace=WS)
    assert result["outcome"] == "unchanged" and result["changed"] == [] and result["ok"] is False


def test_earlier_failure_of_unchanged_artifact_keeps_ok_false(app_dir, stand):
    stand(artifacts=[_art("process/bpmn$p", "DEPLOY_FAILED"), _art("ui/form$f", "DEPLOYED")])
    history = [*_failed("08:30:00.0", "process/bpmn$p", "JAXP00010003: entity over 100,000", trace="t-b"),
               *UPLOAD_CHANGED, START, *_deployed("ui/form$f")]
    with _with_log(history):
        result = app_deploy.deploy(str(app_dir), workspace=WS)
    assert result["outcome"] == "deployed" and result["ok"] is False
    assert result["failed_artifacts"] == ["process/bpmn$p"] and "earlier upload" in result["hint"]
    assert result["earlier_errors"] == {"process/bpmn$p": ["JAXP00010003: entity over 100,000"]}


def test_without_log_the_result_is_unconfirmed(app_dir, stand):
    stand(artifacts=[_art("ui/form$f", "DEPLOYED")])
    with patch("lib.app_deploy.log_command", return_value=None):
        result = app_deploy.deploy(str(app_dir), workspace=WS)
    assert result["ok"] is False and result["outcome"] == "unconfirmed"


def test_patch_deployed_carries_a_note(app_dir, stand):
    stand(artifacts=[_art("app/patch$seed", "DEPLOYED")])
    with _with_log(UPLOAD_CHANGED + [START, *_deployed("app/patch$seed")]):
        result = app_deploy.deploy(str(app_dir), workspace=WS)
    assert "registered" in result["changed"][0]["note"]


def test_log_command_from_environment(monkeypatch):
    monkeypatch.setenv(app_deploy.EAPPS_LOG_CMD_ENV, "ssh host docker logs --since {since} eapps")
    assert app_deploy.log_command("2026-11-10T09:00:00Z") == [
        "ssh", "host", "docker", "logs", "--since", "2026-11-10T09:00:00Z", "eapps"]


# ---------------------------------------------------------------- commit

def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_every_deploy_makes_its_own_commit(app_dir, stand):
    _git("init", "-q", cwd=app_dir)
    _git("config", "user.email", "t@example.invalid", cwd=app_dir)
    _git("config", "user.name", "t", cwd=app_dir)
    stand(artifacts=[_art("model/type$deal", "DEPLOYED")])
    with _with_log(UPLOAD_CHANGED + [START, *_deployed("model/type$deal")]):
        first = app_deploy.deploy(str(app_dir), workspace=WS)
    assert first["commit"]["files_changed"] is True and first["commit"]["hash"]
    with _with_log(UNCHANGED):
        again = app_deploy.deploy(str(app_dir), workspace=WS)
    assert again["commit"]["files_changed"] is False and again["commit"]["hash"] != first["commit"]["hash"]
    log = subprocess.run(["git", "log", "--format=%s"], cwd=app_dir, capture_output=True, text=True).stdout.splitlines()
    assert log[0].startswith(f"deploy {APP} ") and log[0].endswith(": unchanged, 0 changed, 0 failed [confirmed]")
    assert log[1].endswith(": deployed, 1 changed, 0 failed [confirmed]")


def test_deploy_commit_does_not_carry_changes_staged_outside_the_app(app_dir, stand):
    repo = app_dir.parent
    _git("init", "-q", cwd=repo)
    _git("config", "user.email", "t@example.invalid", cwd=repo)
    _git("config", "user.name", "t", cwd=repo)
    (repo / "other.txt").write_text("not part of the application\n")
    _git("add", "other.txt", cwd=repo)
    stand(artifacts=[_art("model/type$deal", "DEPLOYED")])
    with _with_log(UPLOAD_CHANGED + [START, *_deployed("model/type$deal")]):
        result = app_deploy.deploy(str(app_dir), workspace=WS)
    assert "outside the application directory" in result["commit"]["error"]
    assert "other.txt" in result["commit"]["error"]
    log = subprocess.run(["git", "log", "--format=%s"], cwd=repo, capture_output=True, text=True)
    assert log.stdout.strip() == ""


def test_staged_change_outside_the_app_is_seen_with_relative_diff_configured(app_dir, stand):
    repo = app_dir.parent
    _git("init", "-q", cwd=repo)
    _git("config", "user.email", "t@example.invalid", cwd=repo)
    _git("config", "user.name", "t", cwd=repo)
    _git("config", "diff.relative", "true", cwd=repo)
    (repo / "other.txt").write_text("not part of the application\n")
    _git("add", "other.txt", cwd=repo)
    stand(artifacts=[_art("model/type$deal", "DEPLOYED")])
    with _with_log(UPLOAD_CHANGED + [START, *_deployed("model/type$deal")]):
        result = app_deploy.deploy(str(app_dir), workspace=WS)
    assert "other.txt" in result["commit"]["error"]


def test_file_moved_into_the_app_from_outside_is_not_committed_as_a_deletion_outside(app_dir, stand):
    repo = app_dir.parent
    _git("init", "-q", cwd=repo)
    _git("config", "user.email", "t@example.invalid", cwd=repo)
    _git("config", "user.name", "t", cwd=repo)
    (repo / "notes.md").write_text("a file of the surrounding repository\n" * 20)
    _git("add", "notes.md", cwd=repo)
    _git("commit", "-q", "-m", "base", cwd=repo)
    _git("mv", "notes.md", "app/notes.md", cwd=repo)
    stand(artifacts=[_art("model/type$deal", "DEPLOYED")])
    with _with_log(UPLOAD_CHANGED + [START, *_deployed("model/type$deal")]):
        result = app_deploy.deploy(str(app_dir), workspace=WS)
    assert "notes.md" in result["commit"]["error"]
    log = subprocess.run(["git", "log", "--format=%s"], cwd=repo, capture_output=True, text=True)
    assert log.stdout.splitlines() == ["base"]


def test_no_git_no_commit(app_dir, stand):
    stand(artifacts=[_art("model/type$deal", "DEPLOYED")])
    with _with_log(UPLOAD_CHANGED + [START, *_deployed("model/type$deal")]):
        result = app_deploy.deploy(str(app_dir), workspace=WS)
    assert result["commit"] is None


# ---------------------------------------------------------------- MCP layer

async def test_deploy_app_tool_turns_refusal_into_result(client, app_dir, stand):
    stand(global_apps={APP})
    config_dir = tempfile.mkdtemp()
    save_credentials(profile="default", url="http://localhost", username="admin", password="admin",
                     auth_method="basic", config_dir=config_dir)
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir):
        result = (await client.call_tool("deploy_app", {"app_dir": str(app_dir), "workspace": WS})).data
    assert result["ok"] is False and result["outcome"] == "refused"


def test_parse_ignores_the_previous_deploy_read_with_the_time_margin():
    # Live 2026-11-10: the log margin caught the previous deploy's "doesn't change" one second earlier.
    previous = [_line("09:34:30.1", f"Upload application '{APP}'", trace="t-prev"),
                _line("09:34:30.2", f"Application content doesn't change. App ID: '{APP}'", trace="t-prev")]
    parsed = app_deploy.parse_upload_log(previous + UPLOAD_CHANGED + [START, *_deployed("ui/form$f")], SRC, APP)
    assert parsed["unchanged"] is False and parsed["changed"] == ["ui/form$f"]



# ---------------------------------------------------------------- Codex review, round 2

def test_stale_own_status_and_namesake_line_do_not_finish(app_dir, stand):
    # Records still shows the previous upload's DEPLOYED (saved before this revision); a namesake's
    # DEPLOYED line in another workspace must not settle it.
    stand(artifacts=[_art("ui/form$f", "DEPLOYED", modified="2026-11-10T09:00:00Z")])
    with _with_log(UPLOAD_CHANGED + [START, _revision("09:34:37.1", "ui/form$f"),
                                     _status("09:34:37.2", "ui/form$f", "DRAFT", "DEPLOYED", trace="t-other")]):
        result = app_deploy.deploy(str(app_dir), workspace=WS, wait_seconds=60)
    assert result["ok"] is False and result["outcome"] == "timeout" and result["pending"] == ["ui/form$f"]


def test_own_revision_not_yet_in_records_stays_pending(app_dir, stand):
    stand(artifacts=[])
    with _with_log(UPLOAD_CHANGED + [START, _revision("09:34:37.1", "ui/form$new")]):
        result = app_deploy.deploy(str(app_dir), workspace=WS, wait_seconds=60)
    assert result["ok"] is False and result["pending"] == ["ui/form$new"]


def test_unchanged_while_an_artifact_is_still_draft_is_not_ok(app_dir, stand):
    stand(artifacts=[_art("process/bpmn$p", "DRAFT")])
    with _with_log(UNCHANGED):
        result = app_deploy.deploy(str(app_dir), workspace=WS, wait_seconds=60)
    assert result["ok"] is False and result["outcome"] == "timeout" and result["pending"] == ["process/bpmn$p"]


def test_deps_waiting_is_pending_with_its_status(app_dir, stand):
    stand(artifacts=[_art("ui/journal$j", "DEPS_WAITING"), _art("model/type$deal", "DEPLOYED")])
    with _with_log(UPLOAD_CHANGED + [START, *_deployed("model/type$deal")]):
        result = app_deploy.deploy(str(app_dir), workspace=WS, wait_seconds=60)
    assert result["ok"] is False and result["outcome"] == "timeout"
    assert result["pending_statuses"] == {"ui/journal$j": "DEPS_WAITING"}


@pytest.mark.parametrize("content", [
    json.dumps({"id": "p", "target": "ui/menu$m", "workspace": WS}, separators=(",", ":")),
    f"id: p\ntarget: ui/menu$m\nworkspace: >-\n  {WS}\n",
])
def test_artifact_patch_workspace_in_compact_json_and_block_yaml(app_dir, content):
    (app_dir / "artifacts/app/artifact-patch").mkdir(parents=True)
    (app_dir / "artifacts/app/artifact-patch/p.json").write_text(content)
    assert app_deploy.check_artifact_scope(str(app_dir), {WS}) == []


@pytest.mark.parametrize("content, refused", [
    ("type: mutate\nrecords:\n  - id: emodel/gen-ws:template@\n    attributes:\n      formRef: uiserv/form@ecos-crm-form\n", False),
    ("type: mutate\nrecords:\n  - id: emodel/type@CURRENT_WS:x\n    attributes:\n      parentRef: emodel/type@data-list\n", False),
    ("type: mutate\nrecords:\n  - id: emodel/gen-ws:template@\n    attributes:\n      _workspace: other-ws\n", True),
    ('{"type":"mutate","records":[{"id":"uiserv/form@crm-form","attributes":{}}]}', True),
])
def test_patch_data_refs_are_not_targets(app_dir, content, refused):
    (app_dir / "artifacts/app/patch").mkdir(parents=True)
    (app_dir / "artifacts/app/patch/p.yml").write_text(content)
    assert bool(app_deploy.check_artifact_scope(str(app_dir), {WS})) is refused


def test_existing_workspace_system_id_is_known_before_the_scope_check(app_dir, stand):
    stand(sys_id="gen_ws", artifacts=[_art("model/type$deal", "DEPLOYED")])
    (app_dir / "artifacts/app/patch").mkdir(parents=True)
    (app_dir / "artifacts/app/patch/seed.yml").write_text("type: mutate\nrecords:\n  - id: emodel/gen_ws:stage@\n")
    with _with_log(UPLOAD_CHANGED + [_start(src=f"gen_ws:{APP}"),
                                     _revision("09:34:37.1", "model/type$deal", src=f"gen_ws:{APP}"),
                                     _status("09:34:37.2", "model/type$deal", "DRAFT", "DEPLOYED")]):
        result = app_deploy.deploy(str(app_dir), workspace=WS)
    assert result["ok"] is True


# ---------------------------------------------------------------- Codex review, round 3

def _init_git(app_dir):
    _git("init", "-q", cwd=app_dir)
    _git("config", "user.email", "t@example.invalid", cwd=app_dir)
    _git("config", "user.name", "t", cwd=app_dir)
    _git("add", "-A", cwd=app_dir)
    _git("commit", "-qm", "initial", cwd=app_dir)


def test_changed_artifact_files_without_revision_do_not_finish_on_quiet(app_dir, stand):
    # "Start artifacts uploading" is logged before the artifacts are read: quiet proves nothing.
    _init_git(app_dir)
    (app_dir / "artifacts/ui/journal/deals.yml").write_text("id: deals\nname: changed\n")
    stand(artifacts=[_art("ui/journal$deals", "DEPLOYED", modified="2026-11-10T09:00:00Z")])
    with _with_log(UPLOAD_CHANGED + [START]):
        result = app_deploy.deploy(str(app_dir), workspace=WS, wait_seconds=60)
    assert result["ok"] is False and result["outcome"] == "timeout"
    assert result["pending"] == ["<artifact files changed, but no revision seen yet>"]


def test_only_meta_changed_is_confirmed_no_artifact_changes(app_dir, stand):
    _init_git(app_dir)
    _git("commit", "-q", "--allow-empty", "-m",
         f"deploy {APP} 2026-11-10T10:00:00Z: deployed, 2 changed, 0 failed [confirmed]", cwd=app_dir)
    (app_dir / "meta.json").write_text(json.dumps({"id": APP, "name": {"ru": "Новое имя"}, "version": "1.1"}))
    stand(artifacts=[_art("model/type$deal", "DEPLOYED")])
    with _with_log(UPLOAD_CHANGED + [START]):
        result = app_deploy.deploy(str(app_dir), workspace=WS)
    assert result["outcome"] == "no_artifact_changes" and result["ok"] is True


def test_no_artifact_changes_without_git_is_not_confirmed(app_dir, stand):
    stand(artifacts=[_art("model/type$deal", "DEPLOYED")])
    with _with_log(UPLOAD_CHANGED + [START]):
        result = app_deploy.deploy(str(app_dir), workspace=WS)
    assert result["outcome"] == "no_artifact_changes" and result["ok"] is False
    assert "not under git" in result["hint"]


def test_unchanged_after_a_timed_out_deploy_is_not_confirmed(app_dir, stand):
    _init_git(app_dir)
    _git("commit", "-q", "--allow-empty", "-m", f"deploy {APP} 2026-11-10T10:00:00Z: timeout, 1 changed, 0 failed",
         cwd=app_dir)
    stand(artifacts=[_art("ui/journal$deals", "DEPLOYED")])
    with _with_log(UNCHANGED):
        result = app_deploy.deploy(str(app_dir), workspace=WS)
    assert result["outcome"] == "unchanged" and result["ok"] is False and "not confirmed" in result["hint"]


def test_unchanged_after_a_confirmed_deploy_is_ok(app_dir, stand):
    _init_git(app_dir)
    _git("commit", "-q", "--allow-empty", "-m",
         f"deploy {APP} 2026-11-10T10:00:00Z: deployed, 1 changed, 0 failed [confirmed]", cwd=app_dir)
    stand(artifacts=[_art("ui/journal$deals", "DEPLOYED")])
    with _with_log(UNCHANGED):
        assert app_deploy.deploy(str(app_dir), workspace=WS)["ok"] is True


@pytest.mark.parametrize("content, refused", [
    # A type's association target in the written attributes is data, not the patch's target.
    ('{"type":"mutate","config":{"records":[{"id":"emodel/type@gen-ws:contract","attributes":'
     '{"associations":[{"id":"related","target":"emodel/type@case"}]}}]}}', False),
    ("type: mutate\nconfig:\n  records:\n    - id: emodel/type@gen-ws:contract\n      attributes:\n"
     "        associations:\n          - id: related\n            target: emodel/type@case\n", False),
    ("type: mutate\nconfig:\n  records:\n    - id: emodel/type@contract\n", True),
    ("type: mutate\nconfig:\n  records:\n    - id: emodel/gen-ws:stage@\n      attributes:\n        _workspace: other\n", True),
    ("type: mutate\nconfig: [unclosed\n", True),
])
def test_patch_targets_come_from_the_operation_structure(app_dir, content, refused):
    (app_dir / "artifacts/app/patch").mkdir(parents=True)
    (app_dir / "artifacts/app/patch/p.yml").write_text(content)
    assert bool(app_deploy.check_artifact_scope(str(app_dir), {WS})) is refused



# ---------------------------------------------------------------- Codex review, round 4

def test_unconfirmed_state_survives_a_chain_of_repeats(app_dir, stand):
    # timeout -> unchanged (not ok) -> unchanged must still be not ok: nothing was confirmed since.
    _init_git(app_dir)
    _git("commit", "-q", "--allow-empty", "-m",
         f"deploy {APP} 2026-11-10T10:00:00Z: timeout, 2 changed, 0 failed [unconfirmed]", cwd=app_dir)
    stand(artifacts=[_art("model/type$deal", "DEPLOYED")])
    with _with_log(UNCHANGED):
        first = app_deploy.deploy(str(app_dir), workspace=WS)
    with _with_log(UNCHANGED):
        second = app_deploy.deploy(str(app_dir), workspace=WS)
    assert first["ok"] is False and second["ok"] is False
    log = subprocess.run(["git", "log", "--format=%s"], cwd=app_dir, capture_output=True, text=True).stdout
    assert log.splitlines()[0].endswith("[unconfirmed]")


def test_clean_git_before_the_first_deploy_expects_revisions(app_dir, stand):
    _init_git(app_dir)  # committed by the agent, never deployed
    stand(artifacts=[])
    with _with_log(UPLOAD_CHANGED + [START]):
        result = app_deploy.deploy(str(app_dir), workspace=WS, wait_seconds=60)
    assert result["ok"] is False and result["outcome"] == "timeout"


def test_meta_only_change_after_an_unconfirmed_deploy_is_not_ok(app_dir, stand):
    _init_git(app_dir)
    _git("commit", "-q", "--allow-empty", "-m",
         f"deploy {APP} 2026-11-10T10:00:00Z: timeout, 2 changed, 0 failed [unconfirmed]", cwd=app_dir)
    (app_dir / "meta.json").write_text(json.dumps({"id": APP, "name": {"ru": "x"}, "version": "1.2"}))
    stand(artifacts=[_art("model/type$deal", "DEPLOYED")])
    with _with_log(UPLOAD_CHANGED + [START]):
        result = app_deploy.deploy(str(app_dir), workspace=WS, wait_seconds=60)
    assert result["ok"] is False


def test_changes_after_a_confirmed_deploy_are_counted_from_it_not_from_head(app_dir, stand):
    _init_git(app_dir)
    _git("commit", "-q", "--allow-empty", "-m",
         f"deploy {APP} 2026-11-10T10:00:00Z: deployed, 2 changed, 0 failed [confirmed]", cwd=app_dir)
    (app_dir / "artifacts/ui/journal/deals.yml").write_text("id: deals\nname: changed\n")
    _git("commit", "-qam", "agent's own commit", cwd=app_dir)  # HEAD is clean, the stand is not updated
    stand(artifacts=[_art("ui/journal$deals", "DEPLOYED", modified="2026-11-10T09:00:00Z")])
    with _with_log(UPLOAD_CHANGED + [START]):
        result = app_deploy.deploy(str(app_dir), workspace=WS, wait_seconds=60)
    assert result["ok"] is False and result["pending"] == ["<artifact files changed, but no revision seen yet>"]


@pytest.mark.parametrize("content", [
    "type: mutate\nconfig:\n  record:\n    id: emodel/type@case\n",
    "type: mutate\nconfig:\n  record:\n    id: emodel/gen-ws:stage@\n    attributes:\n      _workspace: other\n",
])
def test_single_record_patch_is_checked(app_dir, content):
    (app_dir / "artifacts/app/patch").mkdir(parents=True)
    (app_dir / "artifacts/app/patch/p.yml").write_text(content)
    assert app_deploy.check_artifact_scope(str(app_dir), {WS})



# ---------------------------------------------------------------- pi-run2

def test_access_denied_upload_hints_at_the_deploy_profile(app_dir, stand):
    stand(upload_error="Access denied")
    with _with_log(UPLOAD_CHANGED):
        result = app_deploy.deploy(str(app_dir), workspace=WS, profile="gen-member")
    assert result["outcome"] == "upload_rejected" and "CITECK_DEPLOY_PROFILE" in result["hint"]
    assert "'gen-member'" in result["hint"]


async def test_deploy_app_uses_the_deploy_profile_not_the_active_one(client, app_dir, monkeypatch):
    config_dir = tempfile.mkdtemp()
    for name, user in (("gen-admin", "admin"), ("gen-member", "fet")):
        save_credentials(profile=name, url="http://localhost", username=user, password=user,
                         auth_method="basic", config_dir=config_dir)
    from lib.config import set_active_profile
    set_active_profile("gen-member", config_dir=config_dir)
    monkeypatch.setenv("CITECK_DEPLOY_PROFILE", "gen-admin")
    seen = {}

    def fake_deploy(app_dir, **kwargs):
        seen.update(kwargs)
        return {"ok": True}
    with patch("servers.citeck_mcp._get_config_dir", return_value=config_dir), \
         patch("servers.citeck_mcp.lib_deploy_app", side_effect=fake_deploy):
        await client.call_tool("deploy_app", {"app_dir": str(app_dir), "workspace": WS})
        assert seen["profile"] == "gen-admin"
        await client.call_tool("deploy_app", {"app_dir": str(app_dir), "workspace": WS, "profile": "gen-member"})
        assert seen["profile"] == "gen-member"
