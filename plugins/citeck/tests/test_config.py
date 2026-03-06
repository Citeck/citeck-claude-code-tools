"""Tests for plugins/citeck/lib/config.py"""
import json
import os
import tempfile
import unittest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.config import (
    ConfigError,
    get_active_profile,
    get_credentials,
    get_profiles,
    save_credentials,
    set_active_profile,
)


class TestConfig(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config_dir = self.tmpdir

    def tearDown(self):
        cred_path = os.path.join(self.config_dir, "credentials.json")
        if os.path.exists(cred_path):
            os.remove(cred_path)
        os.rmdir(self.config_dir)

    # --- save and read credentials ---

    def test_save_and_get_credentials(self):
        save_credentials(
            "default", "http://localhost", "admin", "admin",
            client_id="sqa", client_secret="secret",
            config_dir=self.config_dir,
        )
        creds = get_credentials("default", config_dir=self.config_dir)
        self.assertEqual(creds["url"], "http://localhost")
        self.assertEqual(creds["username"], "admin")
        self.assertEqual(creds["password"], "admin")
        self.assertEqual(creds["client_id"], "sqa")
        self.assertEqual(creds["client_secret"], "secret")
        self.assertEqual(creds["auth_method"], "oidc")

    def test_save_minimal_credentials(self):
        save_credentials(
            "basic", "http://localhost", "user", "pass",
            auth_method="basic", config_dir=self.config_dir,
        )
        creds = get_credentials("basic", config_dir=self.config_dir)
        self.assertNotIn("client_id", creds)
        self.assertNotIn("client_secret", creds)
        self.assertEqual(creds["auth_method"], "basic")

    def test_get_credentials_nonexistent_profile(self):
        self.assertIsNone(get_credentials("nonexistent", config_dir=self.config_dir))

    def test_get_credentials_uses_active_profile(self):
        save_credentials(
            "default", "http://localhost", "admin", "admin",
            config_dir=self.config_dir,
        )
        creds = get_credentials(config_dir=self.config_dir)
        self.assertEqual(creds["url"], "http://localhost")

    # --- profiles ---

    def test_get_profiles_empty(self):
        self.assertEqual(get_profiles(config_dir=self.config_dir), [])

    def test_get_profiles_multiple(self):
        save_credentials("dev", "http://dev", "u", "p", config_dir=self.config_dir)
        save_credentials("staging", "http://staging", "u", "p", config_dir=self.config_dir)
        profiles = get_profiles(config_dir=self.config_dir)
        self.assertIn("dev", profiles)
        self.assertIn("staging", profiles)
        self.assertEqual(len(profiles), 2)

    # --- active profile ---

    def test_first_profile_becomes_active(self):
        save_credentials("myprofile", "http://x", "u", "p", config_dir=self.config_dir)
        self.assertEqual(get_active_profile(config_dir=self.config_dir), "myprofile")

    def test_set_active_profile(self):
        save_credentials("dev", "http://dev", "u", "p", config_dir=self.config_dir)
        save_credentials("staging", "http://staging", "u", "p", config_dir=self.config_dir)
        set_active_profile("staging", config_dir=self.config_dir)
        self.assertEqual(get_active_profile(config_dir=self.config_dir), "staging")

    def test_set_active_profile_nonexistent(self):
        with self.assertRaises(ConfigError):
            set_active_profile("nonexistent", config_dir=self.config_dir)

    # --- file permissions ---

    def test_credentials_file_permissions(self):
        save_credentials("default", "http://x", "u", "p", config_dir=self.config_dir)
        path = os.path.join(self.config_dir, "credentials.json")
        mode = os.stat(path).st_mode & 0o777
        self.assertEqual(mode, 0o600)

    # --- edge cases ---

    def test_missing_file_returns_defaults(self):
        self.assertEqual(get_profiles(config_dir=self.config_dir), [])
        self.assertEqual(get_active_profile(config_dir=self.config_dir), "default")

    def test_corrupted_json(self):
        path = os.path.join(self.config_dir, "credentials.json")
        with open(path, "w") as f:
            f.write("{invalid json")
        with self.assertRaises(ConfigError):
            get_credentials(config_dir=self.config_dir)

    def test_invalid_format_not_dict(self):
        path = os.path.join(self.config_dir, "credentials.json")
        with open(path, "w") as f:
            json.dump([1, 2, 3], f)
        with self.assertRaises(ConfigError):
            get_credentials(config_dir=self.config_dir)

    def test_invalid_profiles_not_dict(self):
        path = os.path.join(self.config_dir, "credentials.json")
        with open(path, "w") as f:
            json.dump({"profiles": "bad"}, f)
        with self.assertRaises(ConfigError):
            get_credentials(config_dir=self.config_dir)

    def test_overwrite_existing_profile(self):
        save_credentials("dev", "http://old", "u", "p", config_dir=self.config_dir)
        save_credentials("dev", "http://new", "u2", "p2", config_dir=self.config_dir)
        creds = get_credentials("dev", config_dir=self.config_dir)
        self.assertEqual(creds["url"], "http://new")
        self.assertEqual(creds["username"], "u2")

    def test_second_profile_does_not_change_active(self):
        save_credentials("first", "http://1", "u", "p", config_dir=self.config_dir)
        save_credentials("second", "http://2", "u", "p", config_dir=self.config_dir)
        self.assertEqual(get_active_profile(config_dir=self.config_dir), "first")

    # --- PKCE credentials (no password) ---

    def test_save_pkce_credentials_no_password(self):
        save_credentials(
            "pkce", "http://localhost",
            client_id="nginx", auth_method="oidc-pkce",
            config_dir=self.config_dir,
        )
        creds = get_credentials("pkce", config_dir=self.config_dir)
        self.assertEqual(creds["url"], "http://localhost")
        self.assertEqual(creds["auth_method"], "oidc-pkce")
        self.assertEqual(creds["client_id"], "nginx")
        self.assertNotIn("username", creds)
        self.assertNotIn("password", creds)

    def test_save_credentials_with_discovery_fields(self):
        save_credentials(
            "cloud", "https://citeck.example.com",
            client_id="nginx", auth_method="oidc-pkce",
            realm="Infrastructure",
            eis_id="eis.example.com",
            token_endpoint="https://eis.example.com/auth/realms/Infrastructure/protocol/openid-connect/token",
            authorization_endpoint="https://eis.example.com/auth/realms/Infrastructure/protocol/openid-connect/auth",
            config_dir=self.config_dir,
        )
        creds = get_credentials("cloud", config_dir=self.config_dir)
        self.assertEqual(creds["realm"], "Infrastructure")
        self.assertEqual(creds["eis_id"], "eis.example.com")
        self.assertEqual(creds["token_endpoint"],
                         "https://eis.example.com/auth/realms/Infrastructure/protocol/openid-connect/token")
        self.assertEqual(creds["authorization_endpoint"],
                         "https://eis.example.com/auth/realms/Infrastructure/protocol/openid-connect/auth")

    def test_pkce_and_password_profiles_coexist(self):
        save_credentials(
            "password", "http://localhost", "admin", "admin",
            auth_method="oidc", config_dir=self.config_dir,
        )
        save_credentials(
            "pkce", "http://localhost",
            client_id="nginx", auth_method="oidc-pkce",
            config_dir=self.config_dir,
        )
        pwd_creds = get_credentials("password", config_dir=self.config_dir)
        pkce_creds = get_credentials("pkce", config_dir=self.config_dir)
        self.assertEqual(pwd_creds["username"], "admin")
        self.assertEqual(pwd_creds["password"], "admin")
        self.assertNotIn("username", pkce_creds)
        self.assertNotIn("password", pkce_creds)


if __name__ == "__main__":
    unittest.main()
