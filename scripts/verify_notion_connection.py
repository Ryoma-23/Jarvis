import sys

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app.config import (  # noqa: E402
    NOTION_API_TOKEN,
    NOTION_API_VERSION,
    NOTION_PARENT_PAGE_ID,
)
from app.integrations.notion_client import (  # noqa: E402
    NotionClient,
    NotionConfigurationError,
    NotionError,
)


TEST_PAGE_TITLE_PREFIX = "JARVIS Notion Connection Test"


class NotionVerificationError(NotionError):
    """Raised when API responses do not match the verification request."""


@dataclass(frozen=True)
class NotionVerificationResult:
    parent_page_id: str
    created_page_id: str
    title: str
    url: str


def verify_notion_connection(
    client: NotionClient,
    *,
    parent_page_id: str,
    now: datetime | None = None,
) -> NotionVerificationResult:
    normalized_parent_id = (parent_page_id or "").strip()

    if not normalized_parent_id:
        raise NotionConfigurationError(
            "NOTION_PARENT_PAGE_ID が設定されていません。"
        )

    parent_page = client.retrieve_page(normalized_parent_id)
    retrieved_parent_id = _require_response_text(
        parent_page,
        "id",
        "親ページのレスポンスにPage IDがありません。",
    )

    if not _same_notion_id(retrieved_parent_id, normalized_parent_id):
        raise NotionVerificationError(
            "取得した親ページのIDがNOTION_PARENT_PAGE_IDと一致しません。"
        )

    timestamp = (now or datetime.now().astimezone()).isoformat(
        timespec="seconds"
    )
    title = f"{TEST_PAGE_TITLE_PREFIX} - {timestamp}"
    created_page = client.create_child_page(
        parent_page_id=normalized_parent_id,
        title=title,
    )
    created_page_id = _require_response_text(
        created_page,
        "id",
        "作成レスポンスにPage IDがありません。",
    )

    retrieved_page = client.retrieve_page(created_page_id)
    retrieved_page_id = _require_response_text(
        retrieved_page,
        "id",
        "作成ページの取得レスポンスにPage IDがありません。",
    )

    if not _same_notion_id(retrieved_page_id, created_page_id):
        raise NotionVerificationError(
            "作成したPage IDと再取得したPage IDが一致しません。"
        )

    retrieved_title = _extract_page_title(retrieved_page)

    if retrieved_title != title:
        raise NotionVerificationError(
            "作成したタイトルと再取得したタイトルが一致しません。"
        )

    parent = retrieved_page.get("parent")
    retrieved_child_parent_id = (
        parent.get("page_id")
        if isinstance(parent, dict)
        else None
    )

    if not isinstance(retrieved_child_parent_id, str) or not _same_notion_id(
        retrieved_child_parent_id,
        normalized_parent_id,
    ):
        raise NotionVerificationError(
            "作成ページの親IDがNOTION_PARENT_PAGE_IDと一致しません。"
        )

    url = _require_response_text(
        retrieved_page,
        "url",
        "作成ページの取得レスポンスにURLがありません。",
    )

    return NotionVerificationResult(
        parent_page_id=retrieved_parent_id,
        created_page_id=retrieved_page_id,
        title=retrieved_title,
        url=url,
    )


def main() -> int:
    try:
        client = NotionClient(
            api_token=NOTION_API_TOKEN,
            api_version=NOTION_API_VERSION,
        )
        result = verify_notion_connection(
            client,
            parent_page_id=NOTION_PARENT_PAGE_ID or "",
        )
    except NotionError as error:
        print(f"Notion接続確認に失敗しました: {error}", file=sys.stderr)
        return 1

    print("Notion接続確認に成功しました。")
    print(f"Parent Page ID: {result.parent_page_id}")
    print(f"Created Page ID: {result.created_page_id}")
    print(f"Title: {result.title}")
    print(f"URL: {result.url}")
    print("テストページは確認用としてNotion上に残しています。")
    return 0


def _extract_page_title(page: dict[str, Any]) -> str:
    properties = page.get("properties")

    if not isinstance(properties, dict):
        raise NotionVerificationError(
            "作成ページのレスポンスにpropertiesがありません。"
        )

    for property_value in properties.values():
        if not isinstance(property_value, dict):
            continue

        if property_value.get("type") != "title":
            continue

        title_items = property_value.get("title")

        if not isinstance(title_items, list):
            break

        fragments = []

        for item in title_items:
            if not isinstance(item, dict):
                continue

            plain_text = item.get("plain_text")

            if isinstance(plain_text, str):
                fragments.append(plain_text)
                continue

            text = item.get("text")
            content = text.get("content") if isinstance(text, dict) else None

            if isinstance(content, str):
                fragments.append(content)

        return "".join(fragments)

    raise NotionVerificationError(
        "作成ページのレスポンスにtitleプロパティがありません。"
    )


def _require_response_text(
    payload: dict[str, Any],
    key: str,
    error_message: str,
) -> str:
    value = payload.get(key)

    if not isinstance(value, str) or not value.strip():
        raise NotionVerificationError(error_message)

    return value.strip()


def _same_notion_id(first: str, second: str) -> bool:
    return _canonical_notion_id(first) == _canonical_notion_id(second)


def _canonical_notion_id(value: str) -> str:
    return value.strip().replace("-", "").lower()


if __name__ == "__main__":
    raise SystemExit(main())
