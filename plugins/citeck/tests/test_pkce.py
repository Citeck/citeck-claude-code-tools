"""Tests for plugins/citeck/lib/pkce.py"""
import base64
import hashlib
import http.client
import json
import os
import sys
import threading
import time
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.auth import AuthError
from lib.pkce import (
    generate_pkce_pair,
    generate_state,
    _build_authorization_url,
    _exchange_code,
    CallbackServer,
    CALLBACK_PATH,
)

TOKEN_ENDPOINT = "https://eis.example.com/auth/realms/TestRealm/protocol/openid-connect/token"
AUTH_ENDPOINT = "https://eis.example.com/auth/realms/TestRealm/protocol/openid-connect/auth"


class TestGeneratePkcePair(unittest.TestCase):
    def test_verifier_length(self):
        verifier, _ = generate_pkce_pair()
        self.assertGreaterEqual(len(verifier), 43)

    def test_challenge_is_s256_of_verifier(self):
        verifier, challenge = generate_pkce_pair()
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        self.assertEqual(challenge, expected)

    def test_uniqueness(self):
        pair1 = generate_pkce_pair()
        pair2 = generate_pkce_pair()
        self.assertNotEqual(pair1[0], pair2[0])
        self.assertNotEqual(pair1[1], pair2[1])

    def test_rfc7636_s256(self):
        """Verify S256 computation matches the algorithm from RFC 7636."""
        verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        self.assertEqual(challenge, "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM")


class TestGenerateState(unittest.TestCase):
    def test_non_empty(self):
        state = generate_state()
        self.assertTrue(len(state) > 0)

    def test_uniqueness(self):
        self.assertNotEqual(generate_state(), generate_state())


class TestBuildAuthorizationUrl(unittest.TestCase):
    def test_url_structure(self):
        url = _build_authorization_url(
            AUTH_ENDPOINT, "nginx",
            "http://127.0.0.1:8080/callback",
            "mystate", "mychallenge",
        )
        self.assertTrue(url.startswith(AUTH_ENDPOINT + "?"))
        self.assertIn("response_type=code", url)
        self.assertIn("client_id=nginx", url)
        self.assertIn("state=mystate", url)
        self.assertIn("code_challenge=mychallenge", url)
        self.assertIn("code_challenge_method=S256", url)
        self.assertIn("scope=openid", url)


class TestExchangeCode(unittest.TestCase):
    @patch("lib.pkce.urllib.request.urlopen")
    def test_sends_correct_params(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "access_token": "at",
            "refresh_token": "rt",
            "expires_in": 300,
            "refresh_expires_in": 1800,
        }).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = _exchange_code(
            TOKEN_ENDPOINT, "mycode",
            "http://127.0.0.1:8080/callback", "nginx", "myverifier",
        )
        self.assertEqual(result["access_token"], "at")
        self.assertEqual(result["refresh_token"], "rt")
        self.assertIn("access_expires_at", result)
        self.assertIn("refresh_expires_at", result)

        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.full_url, TOKEN_ENDPOINT)
        body = req.data.decode()
        self.assertIn("grant_type=authorization_code", body)
        self.assertIn("code=mycode", body)
        self.assertIn("code_verifier=myverifier", body)
        self.assertIn("client_id=nginx", body)


class TestCallbackServer(unittest.TestCase):
    def test_port_assigned(self):
        server = CallbackServer()
        try:
            self.assertGreater(server.port, 0)
        finally:
            server.shutdown()

    def test_receives_callback(self):
        server = CallbackServer()
        try:
            port = server.port

            def send_callback():
                time.sleep(0.2)
                conn = http.client.HTTPConnection("127.0.0.1", port)
                conn.request("GET", "/callback?code=abc&state=xyz")
                conn.getresponse()
                conn.close()

            t = threading.Thread(target=send_callback)
            t.start()

            result = server.wait_for_callback(timeout=5)
            t.join()
            self.assertEqual(result["code"], "abc")
            self.assertEqual(result["state"], "xyz")
        finally:
            server.shutdown()

    def test_receives_error_callback(self):
        server = CallbackServer()
        try:
            port = server.port

            def send_callback():
                time.sleep(0.2)
                conn = http.client.HTTPConnection("127.0.0.1", port)
                conn.request("GET", "/callback?error=access_denied&error_description=User+denied")
                conn.getresponse()
                conn.close()

            t = threading.Thread(target=send_callback)
            t.start()

            result = server.wait_for_callback(timeout=5)
            t.join()
            self.assertIn("error", result)
            self.assertIn("denied", result["error"])
        finally:
            server.shutdown()

    def test_timeout(self):
        server = CallbackServer()
        try:
            with self.assertRaises(AuthError) as ctx:
                server.wait_for_callback(timeout=1)
            self.assertIn("Timed out", str(ctx.exception))
        finally:
            server.shutdown()


class TestAuthorize(unittest.TestCase):
    @patch("lib.pkce.webbrowser.open")
    @patch("lib.pkce._exchange_code")
    def test_full_flow(self, mock_exchange, mock_browser):
        mock_exchange.return_value = {
            "access_token": "at",
            "refresh_token": "rt",
            "access_expires_at": time.time() + 300,
            "refresh_expires_at": time.time() + 1800,
        }

        from lib.pkce import authorize, CallbackServer

        original_init = CallbackServer.__init__

        def patched_init(self_server):
            original_init(self_server)
            port = self_server.port

            def send_callback():
                time.sleep(0.3)
                conn = http.client.HTTPConnection("127.0.0.1", port)
                # We need to get the state from the browser URL
                call_args = mock_browser.call_args
                if call_args:
                    import urllib.parse
                    url = call_args[0][0]
                    parsed = urllib.parse.urlparse(url)
                    params = urllib.parse.parse_qs(parsed.query)
                    state = params.get("state", [""])[0]
                else:
                    state = "unknown"
                conn.request("GET", f"/callback?code=testcode&state={state}")
                conn.getresponse()
                conn.close()

            threading.Thread(target=send_callback, daemon=True).start()

        with patch.object(CallbackServer, "__init__", patched_init):
            result = authorize(TOKEN_ENDPOINT, AUTH_ENDPOINT, "nginx", timeout=5)

        self.assertEqual(result["access_token"], "at")
        mock_browser.assert_called_once()
        mock_exchange.assert_called_once()


if __name__ == "__main__":
    unittest.main()
