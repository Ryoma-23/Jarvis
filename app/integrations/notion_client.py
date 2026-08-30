import ssl
import sys

from collections.abc import Mapping
from typing import Any

import requests

from requests.adapters import HTTPAdapter


NOTION_API_BASE_URL = "https://api.notion.com/v1"
DEFAULT_NOTION_API_VERSION = "2026-03-11"
DEFAULT_NOTION_TIMEOUT_SECONDS = 10.0


class NotionError(RuntimeError):
    """Base exception for safe, user-facing Notion errors."""


class NotionConfigurationError(NotionError):
    """Raised when required local Notion configuration is missing."""


class NotionConnectionError(NotionError):
    """Raised when an HTTP response cannot be received from Notion."""


class NotionAPIError(NotionError):
    """Base exception for error responses returned by Notion."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        error_code: str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


class NotionAuthenticationError(NotionAPIError):
    """Raised for a 401 response."""


class NotionPermissionError(NotionAPIError):
    """Raised for a 403 response."""


class NotionResourceNotFoundError(NotionAPIError):
    """Raised for a 404 response."""


class NotionRateLimitError(NotionAPIError):
    """Raised for a 429 response."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        error_code: str | None = None,
        retry_after: str | None = None,
    ):
        super().__init__(
            message,
            status_code=status_code,
            error_code=error_code,
        )
        self.retry_after = retry_after


class NotionServerError(NotionAPIError):
    """Raised for a 5xx response."""


class NotionResponseError(NotionError):
    """Raised when Notion returns a successful but invalid JSON response."""


class _SystemTrustHTTPAdapter(HTTPAdapter):
    def __init__(self, ssl_context: ssl.SSLContext):
        self._ssl_context = ssl_context
        super().__init__()

    def build_connection_pool_key_attributes(
        self,
        request,
        verify,
        cert=None,
    ):
        host_params, pool_kwargs = super().build_connection_pool_key_attributes(
            request,
            verify,
            cert,
        )

        if verify is True:
            pool_kwargs["ssl_context"] = self._ssl_context

        return host_params, pool_kwargs


def _create_default_session() -> requests.Session:
    session = requests.Session()

    if sys.platform != "win32":
        return session

    ssl_context = ssl.create_default_context()
    strict_flag = getattr(ssl, "VERIFY_X509_STRICT", 0)

    if strict_flag:
        ssl_context.verify_flags &= ~strict_flag

    session.mount(
        "https://",
        _SystemTrustHTTPAdapter(ssl_context),
    )
    return session


class NotionClient:
    def __init__(
        self,
        *,
        api_token: str | None,
        api_version: str = DEFAULT_NOTION_API_VERSION,
        timeout_seconds: float = DEFAULT_NOTION_TIMEOUT_SECONDS,
        session: requests.Session | None = None,
    ):
        normalized_token = (api_token or "").strip()
        normalized_version = (api_version or "").strip()

        if not normalized_token:
            raise NotionConfigurationError(
                "NOTION_API_TOKEN が設定されていません。"
            )

        if not normalized_version:
            raise NotionConfigurationError(
                "NOTION_API_VERSION が設定されていません。"
            )

        if timeout_seconds <= 0:
            raise NotionConfigurationError(
                "Notion APIのタイムアウトは0より大きい値が必要です。"
            )

        self._api_token = normalized_token
        self._api_version = normalized_version
        self._timeout_seconds = timeout_seconds
        self._session = session or _create_default_session()

    def __repr__(self) -> str:
        return (
            "NotionClient("
            f"api_version={self._api_version!r}, "
            f"timeout_seconds={self._timeout_seconds!r}"
            ")"
        )

    def retrieve_page(self, page_id: str) -> dict[str, Any]:
        normalized_page_id = self._require_text(page_id, "page_id")
        return self._request("GET", f"/pages/{normalized_page_id}")

    def retrieve_database(self, database_id: str) -> dict[str, Any]:
        normalized_database_id = self._require_text(
            database_id,
            "database_id",
        )
        return self._request(
            "GET",
            f"/databases/{normalized_database_id}",
        )

    def retrieve_data_source(
        self,
        data_source_id: str,
    ) -> dict[str, Any]:
        normalized_data_source_id = self._require_text(
            data_source_id,
            "data_source_id",
        )
        return self._request(
            "GET",
            f"/data_sources/{normalized_data_source_id}",
        )

    def create_database(
        self,
        *,
        parent_page_id: str,
        title: str,
        properties: dict[str, Any],
        is_inline: bool = True,
    ) -> dict[str, Any]:
        normalized_parent_id = self._require_text(
            parent_page_id,
            "parent_page_id",
        )
        normalized_title = self._require_text(title, "title")

        if not isinstance(properties, dict) or not properties:
            raise NotionConfigurationError(
                "Data Sourceのpropertiesが指定されていません。"
            )

        return self._request(
            "POST",
            "/databases",
            json_body={
                "parent": {
                    "type": "page_id",
                    "page_id": normalized_parent_id,
                },
                "title": [
                    {
                        "type": "text",
                        "text": {
                            "content": normalized_title,
                        },
                    }
                ],
                "is_inline": is_inline,
                "initial_data_source": {
                    "properties": properties,
                },
            },
        )

    def create_child_page(
        self,
        *,
        parent_page_id: str,
        title: str,
    ) -> dict[str, Any]:
        normalized_parent_id = self._require_text(
            parent_page_id,
            "parent_page_id",
        )
        normalized_title = self._require_text(title, "title")

        return self._request(
            "POST",
            "/pages",
            json_body={
                "parent": {
                    "type": "page_id",
                    "page_id": normalized_parent_id,
                },
                "properties": {
                    "title": {
                        "type": "title",
                        "title": [
                            {
                                "type": "text",
                                "text": {
                                    "content": normalized_title,
                                },
                            }
                        ],
                    }
                },
            },
        )

    def create_data_source_page(
        self,
        *,
        data_source_id: str,
        properties: dict[str, Any],
    ) -> dict[str, Any]:
        normalized_data_source_id = self._require_text(
            data_source_id,
            "data_source_id",
        )

        if not isinstance(properties, dict) or not properties:
            raise NotionConfigurationError(
                "Pageのpropertiesが指定されていません。"
            )

        return self._request(
            "POST",
            "/pages",
            json_body={
                "parent": {
                    "type": "data_source_id",
                    "data_source_id": normalized_data_source_id,
                },
                "properties": properties,
            },
        )

    def update_page(
        self,
        page_id: str,
        *,
        properties: dict[str, Any] | None = None,
        in_trash: bool | None = None,
    ) -> dict[str, Any]:
        normalized_page_id = self._require_text(page_id, "page_id")
        body: dict[str, Any] = {}

        if properties is not None:
            if not isinstance(properties, dict) or not properties:
                raise NotionConfigurationError(
                    "更新するPageのpropertiesが指定されていません。"
                )

            body["properties"] = properties

        if in_trash is not None:
            if not isinstance(in_trash, bool):
                raise NotionConfigurationError(
                    "in_trashは真偽値で指定してください。"
                )

            body["in_trash"] = in_trash

        if not body:
            raise NotionConfigurationError(
                "Pageの更新内容が指定されていません。"
            )

        return self._request(
            "PATCH",
            f"/pages/{normalized_page_id}",
            json_body=body,
        )

    def query_data_source(
        self,
        data_source_id: str,
        *,
        filter_body: dict[str, Any] | None = None,
        sorts: list[dict[str, Any]] | None = None,
        start_cursor: str | None = None,
        page_size: int = 100,
    ) -> dict[str, Any]:
        normalized_data_source_id = self._require_text(
            data_source_id,
            "data_source_id",
        )

        if not 1 <= page_size <= 100:
            raise NotionConfigurationError(
                "Data Source Queryのpage_sizeは1から100の範囲が必要です。"
            )

        body: dict[str, Any] = {"page_size": page_size}

        if filter_body is not None:
            body["filter"] = filter_body

        if sorts is not None:
            if not isinstance(sorts, list):
                raise NotionConfigurationError(
                    "Data Source Queryのsortsはリストで指定してください。"
                )

            body["sorts"] = sorts

        if start_cursor is not None:
            body["start_cursor"] = self._require_text(
                start_cursor,
                "start_cursor",
            )

        return self._request(
            "POST",
            f"/data_sources/{normalized_data_source_id}/query",
            json_body=body,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = self._session.request(
                method,
                f"{NOTION_API_BASE_URL}{path}",
                headers={
                    "Authorization": f"Bearer {self._api_token}",
                    "Notion-Version": self._api_version,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=json_body,
                timeout=self._timeout_seconds,
            )
        except requests.Timeout:
            raise NotionConnectionError(
                "Notion APIへの接続がタイムアウトしました。"
            ) from None
        except requests.RequestException:
            raise NotionConnectionError(
                "Notion APIへ接続できませんでした。"
            ) from None

        payload = self._read_json(response)

        if not 200 <= response.status_code < 300:
            self._raise_api_error(response, payload)

        if not isinstance(payload, Mapping):
            raise NotionResponseError(
                "Notion APIから予期しないJSON形式が返されました。"
            )

        return dict(payload)

    def _read_json(self, response: requests.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            if 200 <= response.status_code < 300:
                raise NotionResponseError(
                    "Notion APIから有効なJSONが返されませんでした。"
                ) from None

            return None

    def _raise_api_error(
        self,
        response: requests.Response,
        payload: Any,
    ) -> None:
        error_code = None
        detail = None

        if isinstance(payload, Mapping):
            raw_code = payload.get("code")
            raw_message = payload.get("message")

            if isinstance(raw_code, str):
                error_code = raw_code

            if isinstance(raw_message, str):
                detail = self._redact_token(raw_message.strip())

        suffix = f" Notion: {detail}" if detail else ""
        status_code = response.status_code

        if status_code == 401:
            raise NotionAuthenticationError(
                "Notion APIの認証に失敗しました。"
                "NOTION_API_TOKENを確認してください。"
                f"{suffix}",
                status_code=status_code,
                error_code=error_code,
            )

        if status_code == 403:
            raise NotionPermissionError(
                "Notion APIへのアクセス権がありません。"
                "対象ページにConnectionが追加されているか確認してください。"
                f"{suffix}",
                status_code=status_code,
                error_code=error_code,
            )

        if status_code == 404:
            raise NotionResourceNotFoundError(
                "Notionの対象ページが見つかりません。"
                "ページIDとConnectionのアクセス権を確認してください。"
                f"{suffix}",
                status_code=status_code,
                error_code=error_code,
            )

        if status_code == 429:
            raise NotionRateLimitError(
                "Notion APIのレート制限に達しました。"
                "時間を置いて再実行してください。"
                f"{suffix}",
                status_code=status_code,
                error_code=error_code,
                retry_after=response.headers.get("Retry-After"),
            )

        if status_code >= 500:
            raise NotionServerError(
                "Notion APIでサーバーエラーが発生しました。"
                "時間を置いて再実行してください。"
                f"{suffix}",
                status_code=status_code,
                error_code=error_code,
            )

        raise NotionAPIError(
            f"Notion APIリクエストが失敗しました（HTTP {status_code}）。"
            f"{suffix}",
            status_code=status_code,
            error_code=error_code,
        )

    def _redact_token(self, value: str) -> str:
        return value.replace(self._api_token, "[REDACTED]")

    @staticmethod
    def _require_text(value: str, name: str) -> str:
        normalized = (value or "").strip()

        if not normalized:
            raise NotionConfigurationError(
                f"{name} が指定されていません。"
            )

        return normalized
