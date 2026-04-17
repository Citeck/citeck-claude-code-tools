"""Tests for lib/rag_api.py — citeck-docs RAG search client."""
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib import config, rag_api


class RagApiTestBase(unittest.TestCase):
    """Base with a temp config dir and two saved profiles."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        config.save_credentials(
            "local",
            url="http://localhost",
            username="admin",
            password="admin",
            config_dir=self.tmpdir,
        )
        config.save_credentials(
            "prod",
            url="https://citeck.example.com",
            username="u",
            password="p",
            config_dir=self.tmpdir,
        )
        # "local" becomes active because it was saved first

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _mock_response(self, data, status=200):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(data).encode("utf-8")
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp


class TestSearchDocsRequest(RagApiTestBase):

    @patch("lib.auth.get_auth_header", return_value="Bearer xyz")
    @patch("lib.rag_api.urllib.request.urlopen")
    def test_hits_search_endpoint(self, mock_urlopen, _mock_auth):
        mock_urlopen.return_value = self._mock_response([])
        rag_api.search_docs("what is a workspace?", config_dir=self.tmpdir)
        req = mock_urlopen.call_args[0][0]
        self.assertTrue(req.full_url.endswith("/gateway/rag/api/rag/search"))
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.get_header("Content-type"), "application/json")
        self.assertEqual(req.get_header("Authorization"), "Bearer xyz")

    @patch("lib.auth.get_auth_header", return_value="Bearer xyz")
    @patch("lib.rag_api.urllib.request.urlopen")
    def test_body_hardcodes_sourcetype_and_repo(self, mock_urlopen, _mock_auth):
        mock_urlopen.return_value = self._mock_response([])
        rag_api.search_docs("q", config_dir=self.tmpdir)
        body = json.loads(mock_urlopen.call_args[0][0].data)
        self.assertEqual(body["query"], "q")
        self.assertEqual(body["sourceType"], "GITLAB")
        self.assertEqual(body["includeRepoIds"], ["citeck-docs"])
        self.assertEqual(body["topK"], 5)
        self.assertEqual(body["threshold"], 0.4)

    @patch("lib.auth.get_auth_header", return_value="Bearer xyz")
    @patch("lib.rag_api.urllib.request.urlopen")
    def test_custom_top_k_and_threshold(self, mock_urlopen, _mock_auth):
        mock_urlopen.return_value = self._mock_response([])
        rag_api.search_docs("q", top_k=10, threshold=0.3, config_dir=self.tmpdir)
        body = json.loads(mock_urlopen.call_args[0][0].data)
        self.assertEqual(body["topK"], 10)
        self.assertEqual(body["threshold"], 0.3)

    @patch("lib.auth.get_auth_header", return_value="Bearer xyz")
    @patch("lib.rag_api.urllib.request.urlopen")
    def test_returns_parsed_list(self, mock_urlopen, _mock_auth):
        payload = [
            {"documentId": "d1", "sourceId": "citeck-docs", "content": "hello",
             "score": 0.9, "metadata": {"file_path": "a.md"}},
        ]
        mock_urlopen.return_value = self._mock_response(payload)
        result = rag_api.search_docs("q", config_dir=self.tmpdir)
        self.assertEqual(result, payload)

    @patch("lib.auth.get_auth_header", return_value="Bearer xyz")
    @patch("lib.rag_api.urllib.request.urlopen")
    def test_non_list_response_raises(self, mock_urlopen, _mock_auth):
        mock_urlopen.return_value = self._mock_response({"oops": True})
        with self.assertRaises(rag_api.RagApiError):
            rag_api.search_docs("q", config_dir=self.tmpdir)


class TestProfileResolution(RagApiTestBase):

    @patch("lib.auth.get_auth_header", return_value="Bearer xyz")
    @patch("lib.rag_api.urllib.request.urlopen")
    def test_explicit_profile_wins(self, mock_urlopen, mock_auth):
        mock_urlopen.return_value = self._mock_response([])
        rag_api.search_docs("q", profile="prod", config_dir=self.tmpdir)
        mock_auth.assert_called_once_with("prod", self.tmpdir)
        req = mock_urlopen.call_args[0][0]
        self.assertTrue(req.full_url.startswith("https://citeck.example.com"))

    @patch("lib.auth.get_auth_header", return_value="Bearer xyz")
    @patch("lib.rag_api.urllib.request.urlopen")
    def test_docs_profile_used_when_set(self, mock_urlopen, mock_auth):
        config.set_docs_profile("prod", self.tmpdir)
        mock_urlopen.return_value = self._mock_response([])
        rag_api.search_docs("q", config_dir=self.tmpdir)
        mock_auth.assert_called_once_with("prod", self.tmpdir)
        req = mock_urlopen.call_args[0][0]
        self.assertTrue(req.full_url.startswith("https://citeck.example.com"))

    @patch("lib.auth.get_auth_header", return_value="Bearer xyz")
    @patch("lib.rag_api.urllib.request.urlopen")
    def test_falls_back_to_active_profile(self, mock_urlopen, mock_auth):
        mock_urlopen.return_value = self._mock_response([])
        rag_api.search_docs("q", config_dir=self.tmpdir)
        mock_auth.assert_called_once_with("local", self.tmpdir)
        req = mock_urlopen.call_args[0][0]
        self.assertTrue(req.full_url.startswith("http://localhost"))

    def test_docs_profile_points_to_missing_profile(self):
        # Write docs_profile directly bypassing set_docs_profile's validation
        import json as _json
        path = os.path.join(self.tmpdir, "credentials.json")
        with open(path, "r") as f:
            data = _json.load(f)
        data["docs_profile"] = "ghost"
        with open(path, "w") as f:
            _json.dump(data, f)
        with self.assertRaises(rag_api.RagApiError) as ctx:
            rag_api.search_docs("q", config_dir=self.tmpdir)
        self.assertIn("ghost", str(ctx.exception))
        self.assertIn("docs_profile", str(ctx.exception))

    def test_explicit_missing_profile(self):
        with self.assertRaises(rag_api.RagApiError) as ctx:
            rag_api.search_docs("q", profile="ghost", config_dir=self.tmpdir)
        self.assertIn("ghost", str(ctx.exception))


class TestErrorHandling(RagApiTestBase):

    @patch("lib.auth.get_auth_header", return_value="Bearer xyz")
    @patch("lib.rag_api.urllib.request.urlopen")
    def test_401_raises_auth_error(self, mock_urlopen, _mock_auth):
        error = urllib.error.HTTPError(
            "http://localhost/gateway/rag/api/rag/search",
            401, "Unauthorized", {}, MagicMock(),
        )
        error.read = lambda: b"not authorized"
        mock_urlopen.side_effect = error
        with self.assertRaises(rag_api.RagAuthenticationError) as ctx:
            rag_api.search_docs("q", config_dir=self.tmpdir)
        self.assertEqual(ctx.exception.status_code, 401)

    @patch("lib.auth.get_auth_header", return_value="Bearer xyz")
    @patch("lib.rag_api.urllib.request.urlopen")
    def test_500_raises_server_error(self, mock_urlopen, _mock_auth):
        error = urllib.error.HTTPError(
            "http://localhost/gateway/rag/api/rag/search",
            500, "Internal Server Error", {}, MagicMock(),
        )
        error.read = lambda: b""
        mock_urlopen.side_effect = error
        with self.assertRaises(rag_api.RagServerError) as ctx:
            rag_api.search_docs("q", config_dir=self.tmpdir)
        self.assertEqual(ctx.exception.status_code, 500)

    @patch("lib.auth.get_auth_header", return_value="Bearer xyz")
    @patch("lib.rag_api.urllib.request.urlopen")
    def test_connection_error(self, mock_urlopen, _mock_auth):
        mock_urlopen.side_effect = urllib.error.URLError("refused")
        with self.assertRaises(rag_api.RagConnectionError):
            rag_api.search_docs("q", config_dir=self.tmpdir)

    @patch("lib.auth.get_auth_header", return_value="Bearer xyz")
    @patch("lib.rag_api.urllib.request.urlopen")
    def test_404_generic_api_error(self, mock_urlopen, _mock_auth):
        error = urllib.error.HTTPError(
            "http://localhost/gateway/rag/api/rag/search",
            404, "Not Found", {}, MagicMock(),
        )
        error.read = lambda: b""
        mock_urlopen.side_effect = error
        with self.assertRaises(rag_api.RagApiError) as ctx:
            rag_api.search_docs("q", config_dir=self.tmpdir)
        self.assertNotIsInstance(ctx.exception, rag_api.RagAuthenticationError)
        self.assertNotIsInstance(ctx.exception, rag_api.RagServerError)
        self.assertEqual(ctx.exception.status_code, 404)


class TestExceptionHierarchy(unittest.TestCase):

    def test_auth_is_subclass(self):
        self.assertTrue(issubclass(rag_api.RagAuthenticationError, rag_api.RagApiError))

    def test_server_is_subclass(self):
        self.assertTrue(issubclass(rag_api.RagServerError, rag_api.RagApiError))

    def test_connection_is_subclass(self):
        self.assertTrue(issubclass(rag_api.RagConnectionError, rag_api.RagApiError))


if __name__ == "__main__":
    unittest.main()
