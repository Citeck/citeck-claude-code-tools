"""Tests for citeck-auth skill scripts (setup, test_connection, switch_profile)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib import config
from lib import auth

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "skills", "citeck-auth", "scripts")


def run_script(name, args, config_dir=None):
    """Run a skill script and return (returncode, stdout, stderr)."""
    env = os.environ.copy()
    if config_dir:
        env["CITECK_CONFIG_DIR"] = config_dir
    cmd = [sys.executable, os.path.join(SCRIPTS_DIR, name)] + args
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return result.returncode, result.stdout, result.stderr


class TestSetupScript(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_setup_saves_credentials(self):
        config.save_credentials(
            profile="test",
            url="http://localhost",
            username="admin",
            password="admin",
            auth_method="oidc",
            config_dir=self.tmpdir,
        )
        creds = config.get_credentials("test", config_dir=self.tmpdir)
        self.assertEqual(creds["url"], "http://localhost")
        self.assertEqual(creds["username"], "admin")
        self.assertEqual(creds["auth_method"], "oidc")

    def test_setup_basic_auth(self):
        config.save_credentials(
            profile="basic",
            url="http://localhost",
            username="user",
            password="pass",
            auth_method="basic",
            config_dir=self.tmpdir,
        )
        creds = config.get_credentials("basic", config_dir=self.tmpdir)
        self.assertEqual(creds["auth_method"], "basic")
        self.assertNotIn("client_id", creds)

    def test_setup_with_client_id(self):
        config.save_credentials(
            profile="oidc",
            url="http://localhost",
            username="admin",
            password="admin",
            client_id="myapp",
            client_secret="secret",
            auth_method="oidc",
            config_dir=self.tmpdir,
        )
        creds = config.get_credentials("oidc", config_dir=self.tmpdir)
        self.assertEqual(creds["client_id"], "myapp")
        self.assertEqual(creds["client_secret"], "secret")

    def test_setup_strips_trailing_slash(self):
        """Verify the lib stores URL as-is (stripping is done by setup.py script)."""
        config.save_credentials(
            profile="test",
            url="http://localhost/",
            username="admin",
            password="admin",
            config_dir=self.tmpdir,
        )
        creds = config.get_credentials("test", config_dir=self.tmpdir)
        self.assertEqual(creds["url"], "http://localhost/")

    def test_setup_script_cli_missing_required_args(self):
        """Test that the setup script fails without required arguments."""
        rc, stdout, stderr = run_script("setup.py", [])
        self.assertNotEqual(rc, 0)

    def test_setup_script_cli_runs(self):
        """Test the actual CLI script runs and produces JSON output."""
        rc, stdout, stderr = run_script("setup.py", [
            "--profile", "clitest",
            "--url", "http://localhost",
            "--username", "admin",
            "--password", "admin",
        ], config_dir=self.tmpdir)
        self.assertEqual(rc, 0, f"stderr: {stderr}")
        output = json.loads(stdout)
        self.assertEqual(output["status"], "ok")
        self.assertEqual(output["profile"], "clitest")
        self.assertEqual(output["url"], "http://localhost")

    def test_setup_script_cli_strips_trailing_slash(self):
        rc, stdout, stderr = run_script("setup.py", [
            "--profile", "clitest",
            "--url", "http://localhost/",
            "--username", "admin",
            "--password", "admin",
        ], config_dir=self.tmpdir)
        self.assertEqual(rc, 0)
        output = json.loads(stdout)
        self.assertEqual(output["url"], "http://localhost")


class TestTestConnectionScript(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        for root, dirs, files in os.walk(self.tmpdir, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(self.tmpdir)

    def test_validate_connection_no_profile(self):
        """validate_connection raises AuthError when no credentials exist."""
        with self.assertRaises(auth.AuthError):
            auth.validate_connection(profile="nonexistent", config_dir=self.tmpdir)

    @unittest.mock.patch("lib.auth.urllib.request.urlopen")
    def test_validate_connection_basic_auth_unreachable(self, mock_urlopen):
        """validate_connection reports failure for unreachable server with basic auth."""
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        config.save_credentials(
            profile="test",
            url="http://127.0.0.1:19999",
            username="admin",
            password="admin",
            auth_method="basic",
            config_dir=self.tmpdir,
        )
        result = auth.validate_connection(profile="test", config_dir=self.tmpdir)
        self.assertFalse(result["ok"])
        self.assertEqual(result["method"], "basic")

    def test_validate_connection_oidc_unreachable(self):
        """validate_connection reports failure for unreachable OIDC endpoint."""
        config.save_credentials(
            profile="test",
            url="http://127.0.0.1:19999",
            username="admin",
            password="admin",
            auth_method="oidc",
            config_dir=self.tmpdir,
        )
        result = auth.validate_connection(profile="test", config_dir=self.tmpdir)
        self.assertFalse(result["ok"])
        self.assertEqual(result["method"], "oidc")


class TestSwitchProfileScript(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        cred_path = os.path.join(self.tmpdir, "credentials.json")
        if os.path.exists(cred_path):
            os.remove(cred_path)
        os.rmdir(self.tmpdir)

    def test_switch_profile(self):
        config.save_credentials("dev", "http://dev", "u", "p", config_dir=self.tmpdir)
        config.save_credentials("staging", "http://staging", "u", "p", config_dir=self.tmpdir)
        config.set_active_profile("staging", config_dir=self.tmpdir)
        self.assertEqual(config.get_active_profile(config_dir=self.tmpdir), "staging")

    def test_switch_to_nonexistent_profile(self):
        with self.assertRaises(config.ConfigError):
            config.set_active_profile("nonexistent", config_dir=self.tmpdir)

    def test_list_profiles(self):
        config.save_credentials("dev", "http://dev", "u", "p", config_dir=self.tmpdir)
        config.save_credentials("staging", "http://staging", "u", "p", config_dir=self.tmpdir)
        profiles = config.get_profiles(config_dir=self.tmpdir)
        self.assertEqual(len(profiles), 2)
        self.assertIn("dev", profiles)
        self.assertIn("staging", profiles)

    def test_switch_profile_script_cli_list(self):
        """Test the actual CLI script --list runs."""
        rc, stdout, stderr = run_script("switch_profile.py", ["--list"])
        self.assertEqual(rc, 0, f"stderr: {stderr}")
        output = json.loads(stdout)
        self.assertIn("profiles", output)
        self.assertIn("active", output)

    def test_switch_profile_script_cli_no_args(self):
        """Test the CLI script with no args shows current state."""
        rc, stdout, stderr = run_script("switch_profile.py", [])
        self.assertEqual(rc, 0, f"stderr: {stderr}")
        output = json.loads(stdout)
        self.assertIn("active", output)


class TestSetupPKCE(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_pkce_saves_credentials_without_password(self):
        """Verify PKCE profile can be saved without username/password."""
        config.save_credentials(
            profile="pkce",
            url="http://localhost",
            client_id="nginx",
            auth_method="oidc-pkce",
            config_dir=self.tmpdir,
        )
        creds = config.get_credentials("pkce", config_dir=self.tmpdir)
        self.assertEqual(creds["auth_method"], "oidc-pkce")
        self.assertEqual(creds["client_id"], "nginx")
        self.assertNotIn("password", creds)
        self.assertNotIn("username", creds)

    def test_pkce_validate_no_token(self):
        """validate_connection for PKCE with no cached tokens reports failure."""
        config.save_credentials(
            profile="pkce",
            url="http://localhost",
            client_id="nginx",
            auth_method="oidc-pkce",
            config_dir=self.tmpdir,
        )
        result = auth.validate_connection(profile="pkce", config_dir=self.tmpdir)
        self.assertFalse(result["ok"])
        self.assertEqual(result["method"], "oidc-pkce")

    def test_pkce_validate_with_cached_token(self):
        """validate_connection for PKCE with valid cached token reports success."""
        import time
        config.save_credentials(
            profile="pkce",
            url="http://localhost",
            client_id="nginx",
            auth_method="oidc-pkce",
            config_dir=self.tmpdir,
        )
        auth._save_cache({
            "access_token": "tok",
            "access_expires_at": time.time() + 600,
        }, "pkce", config_dir=self.tmpdir)
        result = auth.validate_connection(profile="pkce", config_dir=self.tmpdir)
        self.assertTrue(result["ok"])
        self.assertEqual(result["method"], "oidc-pkce")


if __name__ == "__main__":
    unittest.main()
