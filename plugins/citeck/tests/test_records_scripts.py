"""Tests for citeck-records scripts — query.py, mutate.py.

Verifies that refactored scripts correctly use lib/records_api.py
and maintain backward-compatible CLI behavior.
"""
import json
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

# Import the script modules by manipulating path
SCRIPTS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "skills", "citeck-records", "scripts"
)
PLUGIN_ROOT = os.path.join(os.path.dirname(__file__), "..")


class ScriptTestBase(unittest.TestCase):
    """Base class for testing CLI scripts via subprocess."""

    def _run_script(self, script_name, args, env_extra=None):
        """Run a script as subprocess, return (returncode, stdout, stderr)."""
        script_path = os.path.join(SCRIPTS_DIR, script_name)
        env = os.environ.copy()
        if env_extra:
            env.update(env_extra)
        result = subprocess.run(
            [sys.executable, script_path] + args,
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
        return result.returncode, result.stdout, result.stderr


class TestQueryScriptCLI(ScriptTestBase):

    def test_no_args_prints_usage(self):
        rc, stdout, stderr = self._run_script("query.py", [])
        self.assertEqual(rc, 1)
        self.assertIn("Usage:", stdout)

    def test_invalid_json_prints_error(self):
        rc, stdout, stderr = self._run_script("query.py", ["not-json"])
        self.assertEqual(rc, 1)
        self.assertIn("Invalid JSON", stdout)


class TestMutateScriptCLI(ScriptTestBase):

    def test_no_args_prints_usage(self):
        rc, stdout, stderr = self._run_script("mutate.py", [])
        self.assertEqual(rc, 1)
        self.assertIn("Usage:", stdout)

    def test_invalid_json_prints_error(self):
        rc, stdout, stderr = self._run_script("mutate.py", ["not-json"])
        self.assertEqual(rc, 1)
        self.assertIn("Invalid JSON", stdout)


class TestScriptImports(unittest.TestCase):
    """Verify scripts can import from lib/records_api."""

    def test_query_imports_request(self):
        """Verify query.py can resolve lib.records_api."""
        # Verify the file structure is right for lib imports
        self.assertTrue(os.path.exists(os.path.join(PLUGIN_ROOT, "lib", "records_api.py")))
        self.assertTrue(os.path.exists(os.path.join(PLUGIN_ROOT, "lib", "__init__.py")))

    def test_old_auth_removed(self):
        """Verify old auth.py no longer exists in scripts/."""
        old_auth = os.path.join(SCRIPTS_DIR, "auth.py")
        self.assertFalse(os.path.exists(old_auth), "Old auth.py should be removed from scripts/")


class TestQueryScriptWithMockedLib(unittest.TestCase):
    """Test query.py main() logic with mocked records_api."""

    def _import_query_module(self):
        """Import query.py as a module."""
        import importlib.util
        # Ensure plugin root is in path
        plugin_root = os.path.join(os.path.dirname(__file__), "..")
        if plugin_root not in sys.path:
            sys.path.insert(0, plugin_root)
        spec = importlib.util.spec_from_file_location(
            "query_script", os.path.join(SCRIPTS_DIR, "query.py")
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @patch("lib.records_api.request")
    def test_query_success_with_records(self, mock_raw):
        mock_raw.return_value = {"records": [{"id": "r1"}, {"id": "r2"}]}
        module = self._import_query_module()

        import io
        from contextlib import redirect_stdout
        with patch.object(sys, "argv", ["query.py", '{"sourceId":"emodel/type"}']):
            out = io.StringIO()
            with redirect_stdout(out):
                module.main()

        output = out.getvalue()
        self.assertIn("Found 2 records", output)
        mock_raw.assert_called_once()
        call_body = mock_raw.call_args[0][1]
        self.assertEqual(call_body["sourceId"], "emodel/type")

    @patch("lib.records_api.request")
    def test_query_success_single_record(self, mock_raw):
        mock_raw.return_value = {"id": "emodel/type@test", "attributes": {"name": "Test"}}
        module = self._import_query_module()

        import io
        from contextlib import redirect_stdout
        with patch.object(sys, "argv", ["query.py", '{"record":"emodel/type@test"}']):
            out = io.StringIO()
            with redirect_stdout(out):
                module.main()

        output = out.getvalue()
        self.assertIn("Loaded record", output)

    @patch("lib.records_api.request")
    def test_query_api_error(self, mock_raw):
        from lib.records_api import RecordsApiError
        mock_raw.side_effect = RecordsApiError("Connection refused", response_body="details")
        module = self._import_query_module()

        with patch.object(sys, "argv", ["query.py", '{"sourceId":"emodel/type"}']):
            with self.assertRaises(SystemExit) as ctx:
                module.main()
            self.assertEqual(ctx.exception.code, 1)


class TestMutateScriptWithMockedLib(unittest.TestCase):

    def _import_mutate_module(self):
        import importlib.util
        plugin_root = os.path.join(os.path.dirname(__file__), "..")
        if plugin_root not in sys.path:
            sys.path.insert(0, plugin_root)
        spec = importlib.util.spec_from_file_location(
            "mutate_script", os.path.join(SCRIPTS_DIR, "mutate.py")
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @patch("lib.records_api.request")
    def test_mutate_success(self, mock_raw):
        mock_raw.return_value = {"id": "emodel/type@new-123"}
        module = self._import_mutate_module()

        import io
        from contextlib import redirect_stdout
        body = json.dumps({"record": {"id": "emodel/type@", "attributes": {"name": "New"}}})
        with patch.object(sys, "argv", ["mutate.py", body]):
            out = io.StringIO()
            with redirect_stdout(out):
                module.main()

        output = out.getvalue()
        self.assertIn("Mutated record: emodel/type@new-123", output)


if __name__ == "__main__":
    unittest.main()
