"""Tests for lib/records_api.py — shared Records API client."""
import json
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import urllib.error

from lib import config, records_api


class RecordsApiTestBase(unittest.TestCase):
    """Base class with temp config dir and saved credentials."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        config.save_credentials(
            "default",
            url="http://localhost",
            username="admin",
            password="admin",
            client_id="sqa",
            client_secret="secret",
            config_dir=self.tmpdir,
        )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _mock_urlopen(self, response_data, status=200):
        """Create a mock for urllib.request.urlopen returning JSON."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(response_data).encode("utf-8")
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp


class TestRecordsQuery(RecordsApiTestBase):

    @patch("lib.auth.get_auth_header", return_value="Basic YWRtaW46YWRtaW4=")
    @patch("lib.records_api.urllib.request.urlopen")
    def test_basic_query(self, mock_urlopen, mock_auth):
        response = {"records": [{"id": "rec@1", "attributes": {"name": "Test"}}]}
        mock_urlopen.return_value = self._mock_urlopen(response)

        result = records_api.records_query(
            source_id="emodel/ept-issue",
            attributes={"name": "name"},
            config_dir=self.tmpdir,
        )

        self.assertEqual(result, response)
        # Verify the request was made correctly
        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        self.assertTrue(req.full_url.endswith("/gateway/api/records/query"))
        self.assertEqual(req.get_method(), "POST")
        body = json.loads(req.data)
        self.assertEqual(body["query"]["sourceId"], "emodel/ept-issue")
        self.assertEqual(body["query"]["consistency"], "EVENTUAL")
        self.assertEqual(body["version"], 1)
        self.assertEqual(body["attributes"], {"name": "name"})

    @patch("lib.auth.get_auth_header", return_value="Basic YWRtaW46YWRtaW4=")
    @patch("lib.records_api.urllib.request.urlopen")
    def test_query_with_predicate(self, mock_urlopen, mock_auth):
        response = {"records": []}
        mock_urlopen.return_value = self._mock_urlopen(response)

        query = {"t": "eq", "att": "_status", "val": "in-progress"}
        records_api.records_query(
            source_id="emodel/ept-issue",
            query=query,
            attributes={"id": "?localId"},
            config_dir=self.tmpdir,
        )

        body = json.loads(mock_urlopen.call_args[0][0].data)
        self.assertEqual(body["query"]["query"], query)

    @patch("lib.auth.get_auth_header", return_value="Basic YWRtaW46YWRtaW4=")
    @patch("lib.records_api.urllib.request.urlopen")
    def test_query_with_pagination(self, mock_urlopen, mock_auth):
        response = {"records": [], "hasMore": False, "totalCount": 0}
        mock_urlopen.return_value = self._mock_urlopen(response)

        records_api.records_query(
            source_id="emodel/ept-issue",
            page={"maxItems": 10, "skipCount": 0},
            config_dir=self.tmpdir,
        )

        body = json.loads(mock_urlopen.call_args[0][0].data)
        self.assertEqual(body["query"]["page"], {"maxItems": 10, "skipCount": 0})

    @patch("lib.auth.get_auth_header", return_value="Basic YWRtaW46YWRtaW4=")
    @patch("lib.records_api.urllib.request.urlopen")
    def test_query_minimal(self, mock_urlopen, mock_auth):
        """Query with only source_id — no query, no attributes."""
        response = {"records": []}
        mock_urlopen.return_value = self._mock_urlopen(response)

        records_api.records_query(source_id="emodel/type", config_dir=self.tmpdir)

        body = json.loads(mock_urlopen.call_args[0][0].data)
        self.assertEqual(body["query"]["sourceId"], "emodel/type")
        self.assertEqual(body["query"]["consistency"], "EVENTUAL")
        self.assertEqual(body["version"], 1)
        self.assertNotIn("query", body["query"])  # no inner query predicate
        self.assertNotIn("attributes", body)

    @patch("lib.auth.get_auth_header", return_value="Basic YWRtaW46YWRtaW4=")
    @patch("lib.records_api.urllib.request.urlopen")
    def test_query_with_language(self, mock_urlopen, mock_auth):
        response = {"records": []}
        mock_urlopen.return_value = self._mock_urlopen(response)

        records_api.records_query(
            source_id="emodel/ept-issue",
            language="predicate",
            config_dir=self.tmpdir,
        )

        body = json.loads(mock_urlopen.call_args[0][0].data)
        self.assertEqual(body["query"]["language"], "predicate")

    @patch("lib.auth.get_auth_header", return_value="Basic YWRtaW46YWRtaW4=")
    @patch("lib.records_api.urllib.request.urlopen")
    def test_query_with_workspaces(self, mock_urlopen, mock_auth):
        mock_urlopen.return_value = self._mock_urlopen({"records": []})

        records_api.records_query(
            source_id="emodel/ept-issue",
            workspaces=["ECOSDEV"],
            config_dir=self.tmpdir,
        )

        body = json.loads(mock_urlopen.call_args[0][0].data)
        self.assertEqual(body["query"]["workspaces"], ["ECOSDEV"])

    @patch("lib.auth.get_auth_header", return_value="Basic YWRtaW46YWRtaW4=")
    @patch("lib.records_api.urllib.request.urlopen")
    def test_query_with_sort_by(self, mock_urlopen, mock_auth):
        mock_urlopen.return_value = self._mock_urlopen({"records": []})

        sort_by = [{"attribute": "_created", "ascending": False}]
        records_api.records_query(
            source_id="emodel/ept-issue",
            sort_by=sort_by,
            config_dir=self.tmpdir,
        )

        body = json.loads(mock_urlopen.call_args[0][0].data)
        self.assertEqual(body["query"]["sortBy"], sort_by)

    @patch("lib.auth.get_auth_header", return_value="Basic YWRtaW46YWRtaW4=")
    @patch("lib.records_api.urllib.request.urlopen")
    def test_query_no_workspaces_by_default(self, mock_urlopen, mock_auth):
        mock_urlopen.return_value = self._mock_urlopen({"records": []})

        records_api.records_query(source_id="emodel/type", config_dir=self.tmpdir)

        body = json.loads(mock_urlopen.call_args[0][0].data)
        self.assertNotIn("workspaces", body["query"])
        self.assertNotIn("sortBy", body["query"])


class TestRecordsMutate(RecordsApiTestBase):

    @patch("lib.auth.get_auth_header", return_value="Basic YWRtaW46YWRtaW4=")
    @patch("lib.records_api.urllib.request.urlopen")
    def test_mutate_create(self, mock_urlopen, mock_auth):
        response = {"records": [{"id": "emodel/ept-issue@abc-123"}]}
        mock_urlopen.return_value = self._mock_urlopen(response)

        records = [{"id": "emodel/ept-issue@", "attributes": {
            "_type": "emodel/type@ept-issue-task",
            "summary": "New task",
        }}]
        result = records_api.records_mutate(records, config_dir=self.tmpdir)

        self.assertEqual(result, response)
        req = mock_urlopen.call_args[0][0]
        self.assertTrue(req.full_url.endswith("/gateway/api/records/mutate"))
        body = json.loads(req.data)
        self.assertEqual(body["records"], records)

    @patch("lib.auth.get_auth_header", return_value="Basic YWRtaW46YWRtaW4=")
    @patch("lib.records_api.urllib.request.urlopen")
    def test_mutate_update(self, mock_urlopen, mock_auth):
        response = {"records": [{"id": "emodel/ept-issue@abc-123"}]}
        mock_urlopen.return_value = self._mock_urlopen(response)

        records = [{"id": "emodel/ept-issue@abc-123", "attributes": {
            "summary": "Updated title",
        }}]
        result = records_api.records_mutate(records, config_dir=self.tmpdir)

        self.assertEqual(result, response)


class TestErrorHandling(RecordsApiTestBase):

    @patch("lib.auth.get_auth_header", return_value="Basic YWRtaW46YWRtaW4=")
    @patch("lib.records_api.urllib.request.urlopen")
    def test_401_raises_auth_error(self, mock_urlopen, mock_auth):
        error = urllib.error.HTTPError(
            "http://localhost/gateway/api/records/query",
            401, "Unauthorized", {}, MagicMock(read=lambda: b"Not authorized")
        )
        # HTTPError.read() needs to work
        error.read = lambda: b"Not authorized"
        mock_urlopen.side_effect = error

        with self.assertRaises(records_api.AuthenticationError) as ctx:
            records_api.records_query("emodel/type", config_dir=self.tmpdir)

        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(ctx.exception.response_body, "Not authorized")
        self.assertIn("Authentication failed", str(ctx.exception))

    @patch("lib.auth.get_auth_header", return_value="Basic YWRtaW46YWRtaW4=")
    @patch("lib.records_api.urllib.request.urlopen")
    def test_403_raises_auth_error(self, mock_urlopen, mock_auth):
        error = urllib.error.HTTPError(
            "http://localhost/gateway/api/records/query",
            403, "Forbidden", {}, MagicMock(read=lambda: b"Access denied")
        )
        error.read = lambda: b"Access denied"
        mock_urlopen.side_effect = error

        with self.assertRaises(records_api.AuthenticationError) as ctx:
            records_api.records_query("emodel/type", config_dir=self.tmpdir)

        self.assertEqual(ctx.exception.status_code, 403)

    @patch("lib.auth.get_auth_header", return_value="Basic YWRtaW46YWRtaW4=")
    @patch("lib.records_api.urllib.request.urlopen")
    def test_500_raises_server_error(self, mock_urlopen, mock_auth):
        error = urllib.error.HTTPError(
            "http://localhost/gateway/api/records/query",
            500, "Internal Server Error", {}, MagicMock(read=lambda: b"Stack trace...")
        )
        error.read = lambda: b"Stack trace..."
        mock_urlopen.side_effect = error

        with self.assertRaises(records_api.ServerError) as ctx:
            records_api.records_query("emodel/type", config_dir=self.tmpdir)

        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("Server error", str(ctx.exception))

    @patch("lib.auth.get_auth_header", return_value="Basic YWRtaW46YWRtaW4=")
    @patch("lib.records_api.urllib.request.urlopen")
    def test_502_raises_server_error(self, mock_urlopen, mock_auth):
        error = urllib.error.HTTPError(
            "http://localhost/gateway/api/records/query",
            502, "Bad Gateway", {}, MagicMock(read=lambda: b"")
        )
        error.read = lambda: b""
        mock_urlopen.side_effect = error

        with self.assertRaises(records_api.ServerError) as ctx:
            records_api.records_query("emodel/type", config_dir=self.tmpdir)

        self.assertEqual(ctx.exception.status_code, 502)

    @patch("lib.auth.get_auth_header", return_value="Basic YWRtaW46YWRtaW4=")
    @patch("lib.records_api.urllib.request.urlopen")
    def test_404_raises_generic_error(self, mock_urlopen, mock_auth):
        error = urllib.error.HTTPError(
            "http://localhost/gateway/api/records/query",
            404, "Not Found", {}, MagicMock(read=lambda: b"")
        )
        error.read = lambda: b""
        mock_urlopen.side_effect = error

        with self.assertRaises(records_api.RecordsApiError) as ctx:
            records_api.records_query("emodel/type", config_dir=self.tmpdir)

        self.assertNotIsInstance(ctx.exception, records_api.AuthenticationError)
        self.assertNotIsInstance(ctx.exception, records_api.ServerError)
        self.assertEqual(ctx.exception.status_code, 404)

    @patch("lib.auth.get_auth_header", return_value="Basic YWRtaW46YWRtaW4=")
    @patch("lib.records_api.urllib.request.urlopen")
    def test_connection_refused(self, mock_urlopen, mock_auth):
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        with self.assertRaises(records_api.RecordsConnectionError) as ctx:
            records_api.records_query("emodel/type", config_dir=self.tmpdir)

        self.assertIn("Cannot connect", str(ctx.exception))
        self.assertIn("localhost", str(ctx.exception))

    @patch("lib.auth.get_auth_header", return_value="Basic YWRtaW46YWRtaW4=")
    @patch("lib.records_api.urllib.request.urlopen")
    def test_timeout_raises_connection_error(self, mock_urlopen, mock_auth):
        mock_urlopen.side_effect = OSError("Connection timed out")

        with self.assertRaises(records_api.RecordsConnectionError):
            records_api.records_query("emodel/type", config_dir=self.tmpdir)

    def test_no_credentials_raises_error(self):
        empty_dir = tempfile.mkdtemp()
        try:
            with self.assertRaises(records_api.RecordsApiError) as ctx:
                records_api.records_query("emodel/type", config_dir=empty_dir)
            self.assertIn("No credentials found", str(ctx.exception))
        finally:
            import shutil
            shutil.rmtree(empty_dir, ignore_errors=True)


class TestAuthHeaderPropagation(RecordsApiTestBase):

    @patch("lib.auth.get_auth_header", return_value="Bearer eyJhbGciOi...")
    @patch("lib.records_api.urllib.request.urlopen")
    def test_bearer_token_sent(self, mock_urlopen, mock_auth):
        mock_urlopen.return_value = self._mock_urlopen({"records": []})

        records_api.records_query("emodel/type", config_dir=self.tmpdir)

        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.get_header("Authorization"), "Bearer eyJhbGciOi...")

    @patch("lib.auth.get_auth_header", return_value="Bearer eyJhbGciOi...")
    @patch("lib.records_api.urllib.request.urlopen")
    def test_profile_propagated_to_auth(self, mock_urlopen, mock_auth):
        config.save_credentials(
            "staging", url="http://staging.example.com",
            username="user", password="pass", config_dir=self.tmpdir,
        )
        mock_urlopen.return_value = self._mock_urlopen({"records": []})

        records_api.records_query(
            "emodel/type", profile="staging", config_dir=self.tmpdir,
        )

        mock_auth.assert_called_once_with("staging", self.tmpdir)
        req = mock_urlopen.call_args[0][0]
        self.assertTrue(req.full_url.startswith("http://staging.example.com"))

    @patch("lib.auth.get_auth_header", return_value="Basic YWRtaW46YWRtaW4=")
    @patch("lib.records_api.urllib.request.urlopen")
    def test_content_type_json(self, mock_urlopen, mock_auth):
        mock_urlopen.return_value = self._mock_urlopen({})

        records_api.records_mutate([], config_dir=self.tmpdir)

        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.get_header("Content-type"), "application/json")

    @patch("lib.auth.get_auth_header", return_value="Basic YWRtaW46YWRtaW4=")
    @patch("lib.records_api.urllib.request.urlopen")
    def test_custom_timeout(self, mock_urlopen, mock_auth):
        mock_urlopen.return_value = self._mock_urlopen({})

        records_api.records_query("emodel/type", config_dir=self.tmpdir, timeout=60)

        call_args = mock_urlopen.call_args
        timeout = call_args[1].get("timeout") if call_args[1] else None
        self.assertEqual(timeout, 60)


class TestBaseUrlHandling(RecordsApiTestBase):

    @patch("lib.auth.get_auth_header", return_value="Basic YWRtaW46YWRtaW4=")
    @patch("lib.records_api.urllib.request.urlopen")
    def test_trailing_slash_stripped(self, mock_urlopen, mock_auth):
        """URL with trailing slash should not produce double slashes."""
        config.save_credentials(
            "slashed", url="http://localhost/",
            username="admin", password="admin", config_dir=self.tmpdir,
        )
        config.set_active_profile("slashed", self.tmpdir)
        mock_urlopen.return_value = self._mock_urlopen({"records": []})

        records_api.records_query(
            "emodel/type", profile="slashed", config_dir=self.tmpdir,
        )

        req = mock_urlopen.call_args[0][0]
        self.assertIn("http://localhost/gateway/api/records/query", req.full_url)
        self.assertNotIn("//gateway", req.full_url)


class TestExceptionHierarchy(unittest.TestCase):

    def test_auth_error_is_records_api_error(self):
        self.assertTrue(issubclass(records_api.AuthenticationError, records_api.RecordsApiError))

    def test_server_error_is_records_api_error(self):
        self.assertTrue(issubclass(records_api.ServerError, records_api.RecordsApiError))

    def test_connection_error_is_records_api_error(self):
        self.assertTrue(issubclass(records_api.RecordsConnectionError, records_api.RecordsApiError))


if __name__ == "__main__":
    unittest.main()
