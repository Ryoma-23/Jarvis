import unittest

from datetime import datetime, timezone
from unittest.mock import Mock

import requests

from app.integrations import notion_client
from app.integrations.notion_client import (
    DEFAULT_NOTION_API_VERSION,
    NOTION_API_BASE_URL,
    NotionAPIError,
    NotionAuthenticationError,
    NotionClient,
    NotionConfigurationError,
    NotionConnectionError,
    NotionPermissionError,
    NotionRateLimitError,
    NotionResourceNotFoundError,
    NotionResponseError,
    NotionServerError,
)
from scripts.verify_notion_connection import (
    TEST_PAGE_TITLE_PREFIX,
    NotionVerificationError,
    verify_notion_connection,
)


class FakeResponse:
    def __init__(
        self,
        status_code,
        payload=None,
        *,
        headers=None,
        json_error=None,
    ):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self._json_error = json_error

    def json(self):
        if self._json_error is not None:
            raise self._json_error

        return self._payload


class NotionClientTests(unittest.TestCase):
    def test_missing_token_fails_only_when_client_is_created(self):
        with self.assertRaisesRegex(
            NotionConfigurationError,
            "NOTION_API_TOKEN",
        ):
            NotionClient(api_token=None)

    def test_retrieve_page_sends_safe_common_headers_and_timeout(self):
        session = Mock()
        session.request.return_value = FakeResponse(
            200,
            {"object": "page", "id": "page-id"},
        )
        client = NotionClient(
            api_token="secret-token",
            timeout_seconds=7.5,
            session=session,
        )

        result = client.retrieve_page("page-id")

        self.assertEqual(result["id"], "page-id")
        session.request.assert_called_once_with(
            "GET",
            f"{NOTION_API_BASE_URL}/pages/page-id",
            headers={
                "Authorization": "Bearer secret-token",
                "Notion-Version": DEFAULT_NOTION_API_VERSION,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json=None,
            timeout=7.5,
        )
        self.assertNotIn("secret-token", repr(client))

    def test_windows_default_session_uses_system_trust_without_disabling_tls(self):
        ssl_context = Mock()
        ssl_context.verify_flags = notion_client.ssl.VERIFY_X509_STRICT

        with (
            unittest.mock.patch.object(
                notion_client.sys,
                "platform",
                "win32",
            ),
            unittest.mock.patch.object(
                notion_client.ssl,
                "create_default_context",
                return_value=ssl_context,
            ),
        ):
            session = notion_client._create_default_session()

        adapter = session.get_adapter("https://api.notion.com")
        self.assertIsInstance(
            adapter,
            notion_client._SystemTrustHTTPAdapter,
        )
        self.assertIs(adapter._ssl_context, ssl_context)
        self.assertEqual(ssl_context.verify_flags, 0)
        self.assertTrue(session.verify)

    def test_create_child_page_uses_page_parent_and_title_property(self):
        session = Mock()
        session.request.return_value = FakeResponse(
            200,
            {"object": "page", "id": "created-page-id"},
        )
        client = NotionClient(
            api_token="secret-token",
            api_version="2026-03-11",
            session=session,
        )

        result = client.create_child_page(
            parent_page_id="parent-page-id",
            title="Connection Test",
        )

        self.assertEqual(result["id"], "created-page-id")
        request = session.request.call_args
        self.assertEqual(request.args, ("POST", f"{NOTION_API_BASE_URL}/pages"))
        self.assertEqual(
            request.kwargs["json"],
            {
                "parent": {
                    "type": "page_id",
                    "page_id": "parent-page-id",
                },
                "properties": {
                    "title": {
                        "type": "title",
                        "title": [
                            {
                                "type": "text",
                                "text": {"content": "Connection Test"},
                            }
                        ],
                    }
                },
            },
        )

    def test_create_database_uses_initial_data_source_schema(self):
        session = Mock()
        session.request.return_value = FakeResponse(
            200,
            {"object": "database", "id": "database-id"},
        )
        client = NotionClient(
            api_token="secret-token",
            session=session,
        )
        schema = {
            "Title": {"title": {}},
            "Content": {"rich_text": {}},
        }

        client.create_database(
            parent_page_id="parent-page-id",
            title="JARVIS Notes",
            properties=schema,
        )

        request = session.request.call_args
        self.assertEqual(
            request.args,
            ("POST", f"{NOTION_API_BASE_URL}/databases"),
        )
        self.assertEqual(
            request.kwargs["json"],
            {
                "parent": {
                    "type": "page_id",
                    "page_id": "parent-page-id",
                },
                "title": [
                    {
                        "type": "text",
                        "text": {"content": "JARVIS Notes"},
                    }
                ],
                "is_inline": True,
                "initial_data_source": {"properties": schema},
            },
        )

    def test_data_source_query_uses_filter_and_page_size(self):
        session = Mock()
        session.request.return_value = FakeResponse(
            200,
            {"object": "list", "results": []},
        )
        client = NotionClient(
            api_token="secret-token",
            session=session,
        )
        filter_body = {
            "property": "Sync Key",
            "rich_text": {"equals": "sync-key"},
        }

        client.query_data_source(
            "data-source-id",
            filter_body=filter_body,
            page_size=50,
        )

        session.request.assert_called_once_with(
            "POST",
            f"{NOTION_API_BASE_URL}/data_sources/data-source-id/query",
            headers={
                "Authorization": "Bearer secret-token",
                "Notion-Version": DEFAULT_NOTION_API_VERSION,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={"page_size": 50, "filter": filter_body},
            timeout=10.0,
        )

    def test_http_errors_are_mapped_to_specific_safe_exceptions(self):
        cases = (
            (401, NotionAuthenticationError),
            (403, NotionPermissionError),
            (404, NotionResourceNotFoundError),
            (429, NotionRateLimitError),
            (500, NotionServerError),
            (400, NotionAPIError),
        )

        for status_code, exception_type in cases:
            with self.subTest(status_code=status_code):
                session = Mock()
                session.request.return_value = FakeResponse(
                    status_code,
                    {
                        "code": "test_error",
                        "message": "request failed with secret-token",
                    },
                    headers={"Retry-After": "2"},
                )
                client = NotionClient(
                    api_token="secret-token",
                    session=session,
                )

                with self.assertRaises(exception_type) as context:
                    client.retrieve_page("page-id")

                error = context.exception
                self.assertEqual(error.status_code, status_code)
                self.assertEqual(error.error_code, "test_error")
                self.assertNotIn("secret-token", str(error))
                self.assertIn("[REDACTED]", str(error))

                if isinstance(error, NotionRateLimitError):
                    self.assertEqual(error.retry_after, "2")

    def test_network_error_does_not_include_request_exception_details(self):
        session = Mock()
        session.request.side_effect = requests.Timeout(
            "request contained secret-token"
        )
        client = NotionClient(
            api_token="secret-token",
            session=session,
        )

        with self.assertRaises(NotionConnectionError) as context:
            client.retrieve_page("page-id")

        self.assertNotIn("secret-token", str(context.exception))
        self.assertIsNone(context.exception.__cause__)

    def test_successful_response_must_contain_a_json_object(self):
        session = Mock()
        session.request.return_value = FakeResponse(200, ["unexpected"])
        client = NotionClient(
            api_token="secret-token",
            session=session,
        )

        with self.assertRaises(NotionResponseError):
            client.retrieve_page("page-id")

        session.request.return_value = FakeResponse(
            200,
            json_error=ValueError("invalid json"),
        )

        with self.assertRaises(NotionResponseError):
            client.retrieve_page("page-id")


class NotionConnectionVerificationTests(unittest.TestCase):
    def test_verifier_retrieves_parent_creates_and_retrieves_child(self):
        parent_page_id = "11111111-2222-3333-4444-555555555555"
        child_page_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        now = datetime(2026, 8, 30, 12, 34, 56, tzinfo=timezone.utc)
        expected_title = (
            f"{TEST_PAGE_TITLE_PREFIX} - 2026-08-30T12:34:56+00:00"
        )
        client = Mock(spec=NotionClient)
        client.retrieve_page.side_effect = (
            {
                "object": "page",
                "id": parent_page_id.replace("-", ""),
            },
            {
                "object": "page",
                "id": child_page_id,
                "parent": {
                    "type": "page_id",
                    "page_id": parent_page_id.replace("-", ""),
                },
                "properties": {
                    "title": {
                        "type": "title",
                        "title": [
                            {
                                "type": "text",
                                "plain_text": expected_title,
                            }
                        ],
                    }
                },
                "url": "https://www.notion.so/test-page",
            },
        )
        client.create_child_page.return_value = {
            "object": "page",
            "id": child_page_id,
        }

        result = verify_notion_connection(
            client,
            parent_page_id=parent_page_id,
            now=now,
        )

        self.assertEqual(result.created_page_id, child_page_id)
        self.assertEqual(result.title, expected_title)
        self.assertEqual(result.url, "https://www.notion.so/test-page")
        client.create_child_page.assert_called_once_with(
            parent_page_id=parent_page_id,
            title=expected_title,
        )
        self.assertEqual(
            client.retrieve_page.call_args_list[1].args,
            (child_page_id,),
        )

    def test_verifier_rejects_mismatched_child_parent(self):
        client = Mock(spec=NotionClient)
        client.retrieve_page.side_effect = (
            {"id": "parent-id"},
            {
                "id": "child-id",
                "parent": {"type": "page_id", "page_id": "other-parent"},
                "properties": {
                    "title": {
                        "type": "title",
                        "title": [
                            {
                                "plain_text": (
                                    f"{TEST_PAGE_TITLE_PREFIX} - "
                                    "2026-08-30T12:34:56+00:00"
                                )
                            }
                        ],
                    }
                },
                "url": "https://www.notion.so/test-page",
            },
        )
        client.create_child_page.return_value = {"id": "child-id"}

        with self.assertRaisesRegex(
            NotionVerificationError,
            "親ID",
        ):
            verify_notion_connection(
                client,
                parent_page_id="parent-id",
                now=datetime(
                    2026,
                    8,
                    30,
                    12,
                    34,
                    56,
                    tzinfo=timezone.utc,
                ),
            )


if __name__ == "__main__":
    unittest.main()
