"""Tests for citeck-tracker scripts — create, update, query."""
import io
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "skills", "citeck-tracker", "scripts"
)
PLUGIN_ROOT = os.path.join(os.path.dirname(__file__), "..")


def _ensure_plugin_in_path():
    if PLUGIN_ROOT not in sys.path:
        sys.path.insert(0, PLUGIN_ROOT)


def _import_module(script_name, module_name):
    """Import a tracker script as a module."""
    import importlib.util
    _ensure_plugin_in_path()
    spec = importlib.util.spec_from_file_location(
        module_name, os.path.join(SCRIPTS_DIR, script_name)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ScriptCLIBase(unittest.TestCase):
    """Base for testing tracker scripts via subprocess."""

    def _run_script(self, script_name, args):
        script_path = os.path.join(SCRIPTS_DIR, script_name)
        result = subprocess.run(
            [sys.executable, script_path] + args,
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode, result.stdout, result.stderr


# --- query_issues.py tests ---

class TestQueryIssuesCLI(ScriptCLIBase):

    def test_help_flag(self):
        rc, stdout, stderr = self._run_script("query_issues.py", ["--help"])
        self.assertEqual(rc, 0)
        self.assertIn("--project", stdout)
        self.assertIn("--assignee", stdout)
        self.assertIn("--sort", stdout)


class TestQueryIssuesLogic(unittest.TestCase):

    @patch("lib.records_api.records_query")
    def test_query_with_project_only(self, mock_query):
        mock_query.return_value = {
            "records": [
                {"id": "EPT-1", "summary": "Test issue", "status": "to-do",
                 "assignee": "admin", "priority": "300_medium", "type": "emodel/type@ept-issue-task"},
            ]
        }
        module = _import_module("query_issues.py", "query_issues")

        out = io.StringIO()
        with redirect_stdout(out):
            module.main(["--project", "EPT"])

        output = out.getvalue()
        self.assertIn("Found 1 issue", output)
        self.assertIn("EPT-1", output)
        self.assertIn("Test issue", output)

    @patch("lib.records_api.records_query")
    def test_query_with_all_filters(self, mock_query):
        mock_query.return_value = {"records": []}
        module = _import_module("query_issues.py", "query_issues")

        out = io.StringIO()
        with redirect_stdout(out):
            module.main(["--project", "EPT", "--status", "in-progress",
                         "--assignee", "admin", "--type", "bug", "--limit", "5"])

        # Verify query was built with all predicates (no _workspace, handled by workspaces param)
        query = mock_query.call_args.kwargs["query"]
        self.assertEqual(query["t"], "and")
        self.assertEqual(len(query["val"]), 3)  # status + assignee + type
        # Verify workspaces passed separately
        self.assertEqual(mock_query.call_args.kwargs["workspaces"], ["EPT"])

    @patch("lib.records_api.records_query")
    def test_query_api_error(self, mock_query):
        from lib.records_api import RecordsApiError
        mock_query.side_effect = RecordsApiError("Connection refused")
        module = _import_module("query_issues.py", "query_issues")

        with self.assertRaises(SystemExit) as ctx:
            module.main(["--project", "EPT"])
        self.assertEqual(ctx.exception.code, 1)


class TestQueryIssuesBuildQuery(unittest.TestCase):

    def test_build_query_project_only(self):
        """Project-only query produces empty predicate (workspace handled by workspaces param)."""
        module = _import_module("query_issues.py", "query_issues")
        args = module.parse_args(["--project", "EPT"])
        query = module.build_query(args)
        self.assertEqual(query, {})

    def test_build_query_with_status(self):
        module = _import_module("query_issues.py", "query_issues")
        args = module.parse_args(["--project", "EPT", "--status", "done"])
        query = module.build_query(args)
        self.assertEqual(query["t"], "eq")
        self.assertEqual(query["att"], "_status")
        self.assertEqual(query["val"], "done")

    def test_build_query_assignee_prefix(self):
        module = _import_module("query_issues.py", "query_issues")
        args = module.parse_args(["--project", "EPT", "--assignee", "admin"])
        query = module.build_query(args)
        self.assertEqual(query["att"], "implementer")
        self.assertEqual(query["t"], "contains")
        self.assertEqual(query["val"], ["emodel/person@admin"])

    def test_build_query_assignee_already_prefixed(self):
        module = _import_module("query_issues.py", "query_issues")
        args = module.parse_args(["--project", "EPT", "--assignee", "emodel/person@admin"])
        query = module.build_query(args)
        self.assertEqual(query["val"], ["emodel/person@admin"])

    def test_build_query_no_project(self):
        """Query without project should work (no workspace filter)."""
        module = _import_module("query_issues.py", "query_issues")
        args = module.parse_args(["--status", "to-do"])
        query = module.build_query(args)
        self.assertEqual(query["t"], "eq")
        self.assertEqual(query["att"], "_status")

    def test_invalid_type_exits(self):
        module = _import_module("query_issues.py", "query_issues")
        args = module.parse_args(["--project", "EPT", "--type", "invalid"])
        with self.assertRaises(SystemExit):
            module.build_query(args)


class TestQueryIssuesFormat(unittest.TestCase):

    def test_format_issues_table(self):
        module = _import_module("query_issues.py", "query_issues")
        records = [
            {"id": "EPT-1", "type": "emodel/type@ept-issue-task", "status": "to-do",
             "priority": "300_medium", "assignee": "admin", "summary": "Fix bug"},
        ]
        result = module.format_issues(records)
        self.assertIn("EPT-1", result)
        self.assertIn("task", result)
        self.assertIn("Fix bug", result)

    def test_format_issues_empty(self):
        module = _import_module("query_issues.py", "query_issues")
        result = module.format_issues([])
        self.assertIn("No issues found", result)


# --- create_issue.py tests ---

class TestCreateIssueCLI(ScriptCLIBase):

    def test_missing_required_args(self):
        rc, stdout, stderr = self._run_script("create_issue.py", [])
        self.assertNotEqual(rc, 0)
        self.assertIn("--project", stderr)

    def test_help_flag(self):
        rc, stdout, stderr = self._run_script("create_issue.py", ["--help"])
        self.assertEqual(rc, 0)
        self.assertIn("--type", stdout)

    def test_invalid_type(self):
        rc, stdout, stderr = self._run_script("create_issue.py", [
            "--project", "EPT", "--type", "invalid", "--summary", "Test"
        ])
        self.assertNotEqual(rc, 0)
        self.assertIn("invalid choice", stderr)


class TestCreateIssueLogic(unittest.TestCase):

    @patch("lib.records_api.records_load")
    @patch("lib.records_api.records_query")
    def test_dry_run_output(self, mock_query, mock_load):
        mock_query.return_value = {
            "records": [{"attributes": {"id": "emodel/project@some-uuid"}}]
        }
        mock_load.return_value = {
            "records": [{"attributes": {"?json": {"key": "EPT"}}}]
        }
        module = _import_module("create_issue.py", "create_issue")
        out = io.StringIO()
        with redirect_stdout(out):
            module.main(["--project", "EPT", "--type", "task",
                         "--summary", "Test task", "--dry-run"])

        output = out.getvalue()
        self.assertIn("Issue Preview:", output)
        self.assertIn("task", output)
        self.assertIn("EPT", output)
        self.assertIn("Test task", output)
        self.assertIn("emodel/ept-issue@", output)

    @patch("lib.records_api.records_load")
    @patch("lib.records_api.records_query")
    def test_dry_run_with_assignee(self, mock_query, mock_load):
        mock_query.return_value = {
            "records": [{"attributes": {"id": "emodel/project@some-uuid"}}]
        }
        mock_load.return_value = {
            "records": [{"attributes": {"?json": {"key": "EPT"}}}]
        }
        module = _import_module("create_issue.py", "create_issue")
        out = io.StringIO()
        with redirect_stdout(out):
            module.main(["--project", "EPT", "--type", "bug",
                         "--summary", "Bug fix", "--assignee", "admin", "--dry-run"])

        output = out.getvalue()
        self.assertIn("emodel/person@admin", output)
        self.assertIn("bug", output)

    @patch("lib.records_api.records_mutate")
    @patch("lib.records_api.records_load")
    @patch("lib.records_api.records_query")
    def test_create_success(self, mock_query, mock_load, mock_mutate):
        mock_query.return_value = {
            "records": [{"attributes": {"id": "emodel/project@some-uuid"}}]
        }
        mock_load.return_value = {
            "records": [{"attributes": {"?json": {"key": "EPT"}}}]
        }
        mock_mutate.return_value = {
            "records": [{"id": "emodel/ept-issue@EPT-42"}]
        }
        module = _import_module("create_issue.py", "create_issue")

        out = io.StringIO()
        with redirect_stdout(out):
            module.main(["--project", "EPT", "--type", "task",
                         "--summary", "New task", "--priority", "200_high"])

        output = out.getvalue()
        self.assertIn("Created issue: emodel/ept-issue@EPT-42", output)
        mock_mutate.assert_called_once()
        record = mock_mutate.call_args[0][0][0]
        self.assertEqual(record["attributes"]["type?str"], "ept-issue-task")
        self.assertEqual(record["attributes"]["_workspace?str"], "EPT")
        self.assertEqual(record["attributes"]["priority?str"], "200_high")

    @patch("lib.records_api.records_load")
    @patch("lib.records_api.records_query")
    @patch("lib.records_api.records_mutate")
    def test_create_api_error(self, mock_mutate, mock_query, mock_load):
        mock_query.return_value = {
            "records": [{"attributes": {"id": "emodel/project@some-uuid"}}]
        }
        mock_load.return_value = {
            "records": [{"attributes": {"?json": {"key": "EPT"}}}]
        }
        from lib.records_api import RecordsApiError
        mock_mutate.side_effect = RecordsApiError("Server error", response_body="details")
        module = _import_module("create_issue.py", "create_issue")

        with self.assertRaises(SystemExit) as ctx:
            module.main(["--project", "EPT", "--type", "task", "--summary", "Test"])
        self.assertEqual(ctx.exception.code, 1)


class TestCreateIssueBuildRecord(unittest.TestCase):

    def test_build_record_basic(self):
        module = _import_module("create_issue.py", "create_issue")
        args = module.parse_args(["--project", "EPT", "--type", "story",
                                   "--summary", "User story"])
        record = module.build_record(args, "emodel/project@some-uuid", "EPT")
        self.assertEqual(record["id"], "emodel/ept-issue@")
        self.assertEqual(record["attributes"]["type?str"], "ept-issue-story")
        self.assertEqual(record["attributes"]["_workspace?str"], "EPT")
        self.assertEqual(record["attributes"]["summary?str"], "User story")
        self.assertEqual(record["attributes"]["priority?str"], "300_medium")

    def test_build_record_with_all_options(self):
        module = _import_module("create_issue.py", "create_issue")
        args = module.parse_args([
            "--project", "HR", "--type", "epic", "--summary", "Big feature",
            "--description", "Details here", "--priority", "100_urgent",
            "--assignee", "dev1", "--sprint", "sprint-ref-1"
        ])
        record = module.build_record(args, "emodel/project@hr-uuid", "HR")
        attrs = record["attributes"]
        self.assertEqual(attrs["type?str"], "ept-issue-epic")
        self.assertEqual(attrs["_workspace?str"], "HR")
        self.assertEqual(attrs["description?str"], "Details here")
        self.assertEqual(attrs["priority?str"], "100_urgent")
        self.assertEqual(attrs["implementer?str"], "emodel/person@dev1")
        self.assertEqual(attrs["sprint?assoc"], ["emodel/ept-sprint@sprint-ref-1"])


# --- update_issue.py tests ---

class TestUpdateIssueCLI(ScriptCLIBase):

    def test_missing_issue_arg(self):
        rc, stdout, stderr = self._run_script("update_issue.py", [])
        self.assertNotEqual(rc, 0)
        self.assertIn("--issue", stderr)

    def test_help_flag(self):
        rc, stdout, stderr = self._run_script("update_issue.py", ["--help"])
        self.assertEqual(rc, 0)
        self.assertIn("--status", stdout)


class TestUpdateIssueLogic(unittest.TestCase):

    def test_dry_run_output(self):
        module = _import_module("update_issue.py", "update_issue")
        out = io.StringIO()
        with redirect_stdout(out):
            module.main(["--issue", "EPT-123", "--status", "in-progress", "--dry-run"])

        output = out.getvalue()
        self.assertIn("Update Preview:", output)
        self.assertIn("emodel/ept-issue@EPT-123", output)
        self.assertIn("in-progress", output)

    def test_no_attributes_exits(self):
        module = _import_module("update_issue.py", "update_issue")
        with self.assertRaises(SystemExit) as ctx:
            module.main(["--issue", "EPT-123"])
        self.assertEqual(ctx.exception.code, 1)

    @patch("lib.records_api.records_mutate")
    def test_update_success(self, mock_mutate):
        mock_mutate.return_value = {
            "records": [{"id": "emodel/ept-issue@EPT-123"}]
        }
        module = _import_module("update_issue.py", "update_issue")

        out = io.StringIO()
        with redirect_stdout(out):
            module.main(["--issue", "EPT-123", "--status", "done",
                         "--priority", "100_urgent"])

        output = out.getvalue()
        self.assertIn("Updated issue: emodel/ept-issue@EPT-123", output)
        record = mock_mutate.call_args[0][0][0]
        self.assertEqual(record["attributes"]["_state?str"], "done")
        self.assertEqual(record["attributes"]["priority?str"], "100_urgent")

    @patch("lib.records_api.records_mutate")
    def test_update_api_error(self, mock_mutate):
        from lib.records_api import RecordsApiError
        mock_mutate.side_effect = RecordsApiError("Server error")
        module = _import_module("update_issue.py", "update_issue")

        with self.assertRaises(SystemExit) as ctx:
            module.main(["--issue", "EPT-123", "--status", "done"])
        self.assertEqual(ctx.exception.code, 1)


class TestUpdateIssueResolveRef(unittest.TestCase):

    def test_short_id(self):
        module = _import_module("update_issue.py", "update_issue")
        self.assertEqual(
            module.resolve_issue_ref("EPT-123"),
            "emodel/ept-issue@EPT-123"
        )

    def test_full_ref_unchanged(self):
        module = _import_module("update_issue.py", "update_issue")
        ref = "emodel/ept-issue@EPT-123"
        self.assertEqual(module.resolve_issue_ref(ref), ref)


class TestUpdateIssueBuildRecord(unittest.TestCase):

    def test_build_with_multiple_attrs(self):
        module = _import_module("update_issue.py", "update_issue")
        args = module.parse_args([
            "--issue", "EPT-1", "--status", "review",
            "--assignee", "tester", "--summary", "Updated"
        ])
        record = module.build_record(args)
        self.assertEqual(record["id"], "emodel/ept-issue@EPT-1")
        self.assertEqual(record["attributes"]["_state?str"], "review")
        self.assertEqual(record["attributes"]["implementer?str"], "emodel/person@tester")
        self.assertEqual(record["attributes"]["summary?str"], "Updated")

    def test_build_assignee_prefix(self):
        module = _import_module("update_issue.py", "update_issue")
        args = module.parse_args(["--issue", "X-1", "--assignee", "emodel/person@dev"])
        record = module.build_record(args)
        self.assertEqual(record["attributes"]["implementer?str"], "emodel/person@dev")


class TestUpdateIssueFormat(unittest.TestCase):

    def test_format_preview(self):
        module = _import_module("update_issue.py", "update_issue")
        record = {
            "id": "emodel/ept-issue@EPT-1",
            "attributes": {"_workspace?str": "EPT", "_state?str": "done", "priority?str": "200_high"},
        }
        result = module.format_preview(record)
        self.assertIn("Update Preview:", result)
        self.assertIn("Status: done", result)
        self.assertIn("Priority: 200_high", result)


if __name__ == "__main__":
    unittest.main()
