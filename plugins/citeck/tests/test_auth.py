"""Tests for plugins/citeck/lib/auth.py"""
import base64
import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock
import urllib.error

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.auth import (
    AuthError,
    ReauthenticationRequired,
    get_auth_header,
    get_username,
    validate_connection,
    discover_eis,
    discover_oidc_endpoints,
    _load_cache,
    _save_cache,
    _token_cache_path,
    _get_token_endpoint,
    _get_auth_endpoint,
    _basic_auth_header,
    _eis_id_to_base_url,
    _decode_jwt_payload,
    TOKEN_EXPIRY_MARGIN,
    DEFAULT_REALM,
    DEFAULT_EIS_ID,
)
from lib.config import save_credentials


def _setup_profile(config_dir, profile="default", auth_method="oidc"):
    """Helper to create a profile with credentials."""
    kwargs = {
        "profile": profile,
        "url": "http://localhost",
        "username": "admin",
        "password": "admin",
        "auth_method": auth_method,
        "config_dir": config_dir,
    }
    if auth_method == "oidc":
        kwargs["client_id"] = "sqa"
        kwargs["client_secret"] = "secret"
    save_credentials(**kwargs)


def _make_token_response(access_token="tok123", refresh_token="ref456",
                         expires_in=300, refresh_expires_in=1800):
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": expires_in,
        "refresh_expires_in": refresh_expires_in,
    }


class TestTokenCachePath(unittest.TestCase):
    def test_default_path(self):
        path = _token_cache_path("default")
        self.assertIn("tokens/default/token.json", path)

    def test_custom_config_dir(self):
        path = _token_cache_path("staging", config_dir="/tmp/citeck")
        self.assertEqual(path, "/tmp/citeck/tokens/staging/token.json")


class TestTokenCache(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_save_and_load_cache(self):
        data = {"access_token": "tok", "access_expires_at": time.time() + 300}
        _save_cache(data, "default", config_dir=self.tmpdir)
        loaded = _load_cache("default", config_dir=self.tmpdir)
        self.assertEqual(loaded["access_token"], "tok")

    def test_load_missing_cache(self):
        self.assertIsNone(_load_cache("nonexistent", config_dir=self.tmpdir))

    def test_load_corrupted_cache(self):
        path = _token_cache_path("default", config_dir=self.tmpdir)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write("{bad json")
        self.assertIsNone(_load_cache("default", config_dir=self.tmpdir))


class TestBasicAuthHeader(unittest.TestCase):
    def test_encoding(self):
        header = _basic_auth_header("admin", "admin")
        expected = "Basic " + base64.b64encode(b"admin:admin").decode()
        self.assertEqual(header, expected)

    def test_special_chars(self):
        header = _basic_auth_header("user", "p@ss:word")
        expected = "Basic " + base64.b64encode(b"user:p@ss:word").decode()
        self.assertEqual(header, expected)


class TestEisIdToBaseUrl(unittest.TestCase):
    def test_https_domain(self):
        self.assertEqual(_eis_id_to_base_url("eis.example.com"), "https://eis.example.com")

    def test_localhost(self):
        self.assertEqual(_eis_id_to_base_url("localhost:8080"), "http://localhost:8080")

    def test_already_http(self):
        self.assertEqual(_eis_id_to_base_url("http://keycloak:8080"), "http://keycloak:8080")

    def test_already_https(self):
        self.assertEqual(_eis_id_to_base_url("https://eis.example.com"), "https://eis.example.com")

    def test_strips_trailing_slash(self):
        self.assertEqual(_eis_id_to_base_url("eis.example.com/"), "https://eis.example.com")


class TestGetTokenEndpoint(unittest.TestCase):
    def test_uses_stored_endpoint(self):
        creds = {
            "url": "http://localhost",
            "token_endpoint": "https://eis.example.com/auth/realms/MyRealm/protocol/openid-connect/token",
        }
        self.assertEqual(
            _get_token_endpoint(creds),
            "https://eis.example.com/auth/realms/MyRealm/protocol/openid-connect/token",
        )

    def test_fallback_with_realm(self):
        creds = {"url": "http://localhost", "realm": "Infrastructure"}
        endpoint = _get_token_endpoint(creds)
        self.assertEqual(
            endpoint,
            "http://localhost/ecos-idp/auth/realms/Infrastructure/protocol/openid-connect/token",
        )

    def test_fallback_default_realm(self):
        creds = {"url": "http://localhost"}
        endpoint = _get_token_endpoint(creds)
        self.assertEqual(
            endpoint,
            "http://localhost/ecos-idp/auth/realms/ecos-app/protocol/openid-connect/token",
        )

    def test_strips_trailing_slash(self):
        creds = {"url": "http://localhost/"}
        endpoint = _get_token_endpoint(creds)
        self.assertFalse(endpoint.startswith("http://localhost//"))


class TestGetAuthEndpoint(unittest.TestCase):
    def test_uses_stored_endpoint(self):
        creds = {
            "url": "http://localhost",
            "authorization_endpoint": "https://eis.example.com/auth/realms/MyRealm/protocol/openid-connect/auth",
        }
        self.assertEqual(
            _get_auth_endpoint(creds),
            "https://eis.example.com/auth/realms/MyRealm/protocol/openid-connect/auth",
        )

    def test_fallback_with_realm(self):
        creds = {"url": "http://localhost", "realm": "Infrastructure"}
        endpoint = _get_auth_endpoint(creds)
        self.assertIn("/realms/Infrastructure/", endpoint)

    def test_fallback_default_realm(self):
        creds = {"url": "http://localhost"}
        endpoint = _get_auth_endpoint(creds)
        self.assertIn("/realms/ecos-app/", endpoint)


class TestDiscoverEis(unittest.TestCase):
    @patch("lib.auth.urllib.request.urlopen")
    def test_returns_eis_info(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "realmId": "Infrastructure",
            "eisId": "eis.example.com",
            "logoutUrl": "/logout",
        }).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = discover_eis("https://citeck.example.com")
        self.assertEqual(result["realm"], "Infrastructure")
        self.assertEqual(result["eis_id"], "eis.example.com")
        self.assertTrue(result["is_oidc"])

    @patch("lib.auth.urllib.request.urlopen")
    def test_returns_not_oidc_for_eis_id_placeholder(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "realmId": "ecos-app",
            "eisId": "EIS_ID",
        }).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = discover_eis("http://localhost")
        self.assertEqual(result["eis_id"], "EIS_ID")
        self.assertFalse(result["is_oidc"])

    @patch("lib.auth.urllib.request.urlopen")
    def test_fallback_on_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        result = discover_eis("http://localhost")
        self.assertEqual(result["eis_id"], DEFAULT_EIS_ID)
        self.assertEqual(result["realm"], DEFAULT_REALM)
        self.assertFalse(result["is_oidc"])


class TestDiscoverOidcEndpoints(unittest.TestCase):
    @patch("lib.auth.urllib.request.urlopen")
    def test_returns_endpoints(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "token_endpoint": "https://eis.example.com/auth/realms/Infra/protocol/openid-connect/token",
            "authorization_endpoint": "https://eis.example.com/auth/realms/Infra/protocol/openid-connect/auth",
            "issuer": "https://eis.example.com/auth/realms/Infra",
        }).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = discover_oidc_endpoints("eis.example.com", "Infra")
        self.assertIn("token_endpoint", result)
        self.assertIn("authorization_endpoint", result)

        # Verify it constructed the correct well-known URL
        call_args = mock_urlopen.call_args[0][0]
        self.assertIn("https://eis.example.com/auth/realms/Infra/.well-known/openid-configuration",
                       call_args.full_url)

    @patch("lib.auth.urllib.request.urlopen")
    def test_returns_none_on_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        result = discover_oidc_endpoints("eis.example.com", "MyRealm")
        self.assertIsNone(result)


class TestGetAuthHeaderNoCredentials(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_raises_auth_error_without_credentials(self):
        with self.assertRaises(AuthError) as ctx:
            get_auth_header(config_dir=self.tmpdir)
        self.assertIn("No credentials found", str(ctx.exception))


class TestGetAuthHeaderBasicMethod(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        _setup_profile(self.tmpdir, auth_method="basic")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_returns_basic_header_directly(self):
        header = get_auth_header(config_dir=self.tmpdir)
        expected = "Basic " + base64.b64encode(b"admin:admin").decode()
        self.assertEqual(header, expected)


class TestGetAuthHeaderOIDC(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        _setup_profile(self.tmpdir, auth_method="oidc")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    @patch("lib.auth._token_request")
    def test_password_grant_success(self, mock_request):
        mock_request.return_value = _make_token_response()
        header = get_auth_header(config_dir=self.tmpdir)
        self.assertTrue(header.startswith("Bearer "))
        self.assertIn("tok123", header)
        mock_request.assert_called_once()

    @patch("lib.auth._token_request")
    def test_caches_token(self, mock_request):
        mock_request.return_value = _make_token_response()
        get_auth_header(config_dir=self.tmpdir)
        cache = _load_cache("default", config_dir=self.tmpdir)
        self.assertIsNotNone(cache)
        self.assertEqual(cache["access_token"], "tok123")

    def test_uses_cached_token(self):
        future = time.time() + 600
        _save_cache({
            "access_token": "cached_tok",
            "access_expires_at": future,
        }, "default", config_dir=self.tmpdir)
        header = get_auth_header(config_dir=self.tmpdir)
        self.assertEqual(header, "Bearer cached_tok")

    @patch("lib.auth._token_request")
    def test_refresh_grant_when_access_expired(self, mock_request):
        now = time.time()
        _save_cache({
            "access_token": "old_tok",
            "refresh_token": "ref_tok",
            "access_expires_at": now - 10,
            "refresh_expires_at": now + 600,
        }, "default", config_dir=self.tmpdir)
        mock_request.return_value = _make_token_response(access_token="refreshed_tok")
        header = get_auth_header(config_dir=self.tmpdir)
        self.assertEqual(header, "Bearer refreshed_tok")
        args = mock_request.call_args
        self.assertEqual(args[0][1]["grant_type"], "refresh_token")

    @patch("lib.auth._token_request")
    def test_password_grant_when_refresh_expired(self, mock_request):
        now = time.time()
        _save_cache({
            "access_token": "old_tok",
            "refresh_token": "ref_tok",
            "access_expires_at": now - 10,
            "refresh_expires_at": now - 10,
        }, "default", config_dir=self.tmpdir)
        mock_request.return_value = _make_token_response(access_token="new_tok")
        header = get_auth_header(config_dir=self.tmpdir)
        self.assertEqual(header, "Bearer new_tok")
        args = mock_request.call_args
        self.assertEqual(args[0][1]["grant_type"], "password")

    @patch("lib.auth._token_request")
    def test_falls_back_to_basic_on_connection_error(self, mock_request):
        mock_request.side_effect = urllib.error.URLError("Connection refused")
        header = get_auth_header(config_dir=self.tmpdir)
        expected = "Basic " + base64.b64encode(b"admin:admin").decode()
        self.assertEqual(header, expected)

    @patch("lib.auth._token_request")
    def test_http_error_propagates_not_fallback(self, mock_request):
        """HTTP 401 from OIDC means wrong credentials, should raise AuthError not fallback."""
        mock_request.side_effect = urllib.error.HTTPError(
            "http://x", 401, "Unauthorized", {}, None
        )
        with self.assertRaises(AuthError) as ctx:
            get_auth_header(config_dir=self.tmpdir)
        self.assertIn("401", str(ctx.exception))


class TestGetAuthHeaderWithDiscoveredEndpoints(unittest.TestCase):
    """Test that discovered token_endpoint is used correctly."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        save_credentials(
            profile="default",
            url="https://citeck.example.com",
            username="admin",
            password="admin",
            client_id="sqa",
            auth_method="oidc",
            realm="Infrastructure",
            eis_id="eis.example.com",
            token_endpoint="https://eis.example.com/auth/realms/Infrastructure/protocol/openid-connect/token",
            config_dir=self.tmpdir,
        )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    @patch("lib.auth._token_request")
    def test_uses_discovered_token_endpoint(self, mock_request):
        mock_request.return_value = _make_token_response()
        get_auth_header(config_dir=self.tmpdir)
        call_args = mock_request.call_args[0]
        self.assertEqual(
            call_args[0],
            "https://eis.example.com/auth/realms/Infrastructure/protocol/openid-connect/token",
        )


class TestGetAuthHeaderMultiProfile(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        _setup_profile(self.tmpdir, profile="dev", auth_method="basic")
        _setup_profile(self.tmpdir, profile="staging", auth_method="basic")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_explicit_profile(self):
        header = get_auth_header(profile="staging", config_dir=self.tmpdir)
        self.assertTrue(header.startswith("Basic "))

    def test_nonexistent_profile_raises(self):
        with self.assertRaises(AuthError):
            get_auth_header(profile="prod", config_dir=self.tmpdir)


class TestValidateConnection(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    @patch("lib.auth._token_request")
    def test_oidc_success(self, mock_request):
        _setup_profile(self.tmpdir, auth_method="oidc")
        mock_request.return_value = _make_token_response()
        result = validate_connection(config_dir=self.tmpdir)
        self.assertTrue(result["ok"])
        self.assertEqual(result["method"], "oidc")
        self.assertIsNone(result["error"])

    @patch("lib.auth._token_request")
    def test_oidc_failure(self, mock_request):
        _setup_profile(self.tmpdir, auth_method="oidc")
        mock_request.side_effect = urllib.error.URLError("Connection refused")
        result = validate_connection(config_dir=self.tmpdir)
        self.assertFalse(result["ok"])
        self.assertEqual(result["method"], "oidc")
        self.assertIn("Connection refused", result["error"])

    @patch("lib.auth.urllib.request.urlopen")
    def test_basic_success(self, mock_urlopen):
        _setup_profile(self.tmpdir, auth_method="basic")
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"{}"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        result = validate_connection(config_dir=self.tmpdir)
        self.assertTrue(result["ok"])
        self.assertEqual(result["method"], "basic")

    @patch("lib.auth.urllib.request.urlopen")
    def test_basic_failure(self, mock_urlopen):
        _setup_profile(self.tmpdir, auth_method="basic")
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        result = validate_connection(config_dir=self.tmpdir)
        self.assertFalse(result["ok"])
        self.assertEqual(result["method"], "basic")

    def test_no_credentials_raises(self):
        with self.assertRaises(AuthError):
            validate_connection(config_dir=self.tmpdir)


def _setup_pkce_profile(config_dir, profile="default"):
    """Helper to create a PKCE profile (no password)."""
    save_credentials(
        profile=profile,
        url="http://localhost",
        client_id="nginx",
        auth_method="oidc-pkce",
        config_dir=config_dir,
    )


class TestGetAuthHeaderOIDCPKCE(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        _setup_pkce_profile(self.tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_cached_token_works(self):
        future = time.time() + 600
        _save_cache({
            "access_token": "pkce_tok",
            "access_expires_at": future,
        }, "default", config_dir=self.tmpdir)
        header = get_auth_header(config_dir=self.tmpdir)
        self.assertEqual(header, "Bearer pkce_tok")

    @patch("lib.auth._token_request")
    def test_refresh_grant_works(self, mock_request):
        now = time.time()
        _save_cache({
            "access_token": "old",
            "refresh_token": "ref",
            "access_expires_at": now - 10,
            "refresh_expires_at": now + 600,
        }, "default", config_dir=self.tmpdir)
        mock_request.return_value = _make_token_response(access_token="refreshed")
        header = get_auth_header(config_dir=self.tmpdir)
        self.assertEqual(header, "Bearer refreshed")

    def test_raises_reauth_when_no_tokens(self):
        with self.assertRaises(ReauthenticationRequired) as ctx:
            get_auth_header(config_dir=self.tmpdir)
        self.assertIn("citeck:citeck-auth", str(ctx.exception))

    def test_raises_reauth_when_all_expired(self):
        now = time.time()
        _save_cache({
            "access_token": "old",
            "refresh_token": "ref",
            "access_expires_at": now - 10,
            "refresh_expires_at": now - 10,
        }, "default", config_dir=self.tmpdir)
        with self.assertRaises(ReauthenticationRequired):
            get_auth_header(config_dir=self.tmpdir)

    def test_no_basic_fallback(self):
        """PKCE profiles must not fall back to Basic Auth."""
        with self.assertRaises(ReauthenticationRequired):
            get_auth_header(config_dir=self.tmpdir)


class TestValidateConnectionPKCE(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        _setup_pkce_profile(self.tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_valid_cached_token(self):
        future = time.time() + 600
        _save_cache({
            "access_token": "tok",
            "access_expires_at": future,
        }, "default", config_dir=self.tmpdir)
        result = validate_connection(config_dir=self.tmpdir)
        self.assertTrue(result["ok"])
        self.assertEqual(result["method"], "oidc-pkce")

    def test_valid_refresh_token(self):
        now = time.time()
        _save_cache({
            "access_token": "old",
            "refresh_token": "ref",
            "access_expires_at": now - 10,
            "refresh_expires_at": now + 600,
        }, "default", config_dir=self.tmpdir)
        result = validate_connection(config_dir=self.tmpdir)
        self.assertTrue(result["ok"])
        self.assertEqual(result["method"], "oidc-pkce")

    def test_no_valid_token(self):
        result = validate_connection(config_dir=self.tmpdir)
        self.assertFalse(result["ok"])
        self.assertEqual(result["method"], "oidc-pkce")
        self.assertIn("citeck:citeck-auth", result["error"])


def _make_jwt(payload):
    """Create a fake JWT with the given payload dict."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "RS256"}).encode()).rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    sig = base64.urlsafe_b64encode(b"fakesig").rstrip(b"=").decode()
    return f"{header}.{body}.{sig}"


class TestDecodeJwtPayload(unittest.TestCase):
    def test_valid_jwt(self):
        token = _make_jwt({"preferred_username": "roman", "sub": "123"})
        payload = _decode_jwt_payload(token)
        self.assertEqual(payload["preferred_username"], "roman")

    def test_invalid_token(self):
        self.assertIsNone(_decode_jwt_payload("not-a-jwt"))

    def test_empty_string(self):
        self.assertIsNone(_decode_jwt_payload(""))

    def test_two_segments(self):
        self.assertIsNone(_decode_jwt_payload("a.b"))


class TestGetUsername(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_basic_auth_returns_stored_username(self):
        _setup_profile(self.tmpdir, auth_method="basic")
        username = get_username(config_dir=self.tmpdir)
        self.assertEqual(username, "admin")

    def test_oidc_password_returns_stored_username(self):
        _setup_profile(self.tmpdir, auth_method="oidc")
        username = get_username(config_dir=self.tmpdir)
        self.assertEqual(username, "admin")

    def test_pkce_extracts_from_jwt(self):
        _setup_pkce_profile(self.tmpdir)
        jwt = _make_jwt({"preferred_username": "roman.makarskiy"})
        _save_cache({
            "access_token": jwt,
            "access_expires_at": time.time() + 600,
        }, "default", config_dir=self.tmpdir)
        username = get_username(config_dir=self.tmpdir)
        self.assertEqual(username, "roman.makarskiy")

    def test_pkce_no_token_returns_none(self):
        _setup_pkce_profile(self.tmpdir)
        username = get_username(config_dir=self.tmpdir)
        self.assertIsNone(username)

    def test_no_credentials_raises(self):
        with self.assertRaises(AuthError):
            get_username(config_dir=self.tmpdir)


class TestTokenExpiryMargin(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        _setup_profile(self.tmpdir, auth_method="oidc")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    @patch("lib.auth._token_request")
    def test_token_within_margin_triggers_refresh(self, mock_request):
        """Token expiring within TOKEN_EXPIRY_MARGIN seconds should trigger refresh."""
        now = time.time()
        _save_cache({
            "access_token": "about_to_expire",
            "refresh_token": "ref_tok",
            "access_expires_at": now + TOKEN_EXPIRY_MARGIN - 1,
            "refresh_expires_at": now + 600,
        }, "default", config_dir=self.tmpdir)
        mock_request.return_value = _make_token_response(access_token="refreshed")
        header = get_auth_header(config_dir=self.tmpdir)
        self.assertEqual(header, "Bearer refreshed")


if __name__ == "__main__":
    unittest.main()
