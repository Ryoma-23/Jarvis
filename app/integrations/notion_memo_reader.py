from datetime import datetime
from typing import Any

from app.integrations.notion_client import (
    NotionClient,
    NotionConfigurationError,
    NotionResponseError,
)
from app.integrations.notion_memo_writer import (
    CONTENT_PROPERTY,
    CREATED_AT_PROPERTY,
    LOCAL_ID_PROPERTY,
    SOURCE_PROPERTY,
    SYNC_KEY_PROPERTY,
    TITLE_PROPERTY,
    validate_notes_data_source_schema,
)


NOTION_QUERY_PAGE_SIZE = 100
CREATED_AT_ASCENDING_SORT = [
    {
        "property": CREATED_AT_PROPERTY,
        "direction": "ascending",
    }
]


class NotionMemoReader:
    def __init__(
        self,
        *,
        client: NotionClient,
        data_source_id: str,
    ):
        normalized_data_source_id = (data_source_id or "").strip()

        if not normalized_data_source_id:
            raise NotionConfigurationError(
                "Notes用Data Source IDが設定されていません。"
            )

        self._client = client
        self._data_source_id = normalized_data_source_id
        self._schema_validated = False

    @property
    def data_source_id(self) -> str:
        return self._data_source_id

    def validate_schema(self) -> dict[str, Any]:
        data_source = validate_notes_data_source_schema(
            self._client,
            self._data_source_id,
        )
        self._schema_validated = True
        return data_source

    def list_notes(self) -> list[dict[str, Any]]:
        return self._query_all()

    def search_content(self, keyword: str) -> list[dict[str, Any]]:
        normalized_keyword = (keyword or "").strip()

        if not normalized_keyword:
            raise NotionConfigurationError(
                "Memo検索キーワードが指定されていません。"
            )

        return self._query_all(
            filter_body={
                "property": CONTENT_PROPERTY,
                "rich_text": {"contains": normalized_keyword},
            }
        )

    def get_by_local_id(self, note_id: int) -> dict[str, Any] | None:
        notes = self.find_by_local_id(note_id)

        if len(notes) > 1:
            raise NotionResponseError(
                f"Jarvis Local ID {note_id} のMemoが複数見つかりました。"
            )

        return notes[0] if notes else None

    def find_by_local_id(self, note_id: int) -> list[dict[str, Any]]:
        if not isinstance(note_id, int) or isinstance(note_id, bool):
            raise NotionConfigurationError(
                "Jarvis Local IDは整数で指定してください。"
            )

        return self._query_all(
            filter_body={
                "property": LOCAL_ID_PROPERTY,
                "number": {"equals": note_id},
            }
        )

    def get_by_page_id(self, page_id: str) -> dict[str, Any]:
        self._ensure_schema()
        return self._memo_from_page(self._client.retrieve_page(page_id))

    def _query_all(
        self,
        *,
        filter_body: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self._ensure_schema()
        pages = []
        start_cursor = None
        seen_cursors = set()

        while True:
            response = self._client.query_data_source(
                self._data_source_id,
                filter_body=filter_body,
                sorts=CREATED_AT_ASCENDING_SORT,
                start_cursor=start_cursor,
                page_size=NOTION_QUERY_PAGE_SIZE,
            )
            results = response.get("results")
            has_more = response.get("has_more")

            if not isinstance(results, list):
                raise NotionResponseError(
                    "Notes Data Source Queryのresultsを取得できませんでした。"
                )

            if not isinstance(has_more, bool):
                raise NotionResponseError(
                    "Notes Data Source Queryのhas_moreを取得できませんでした。"
                )

            pages.extend(self._memo_from_page(page) for page in results)

            if not has_more:
                return pages

            next_cursor = response.get("next_cursor")

            if (
                not isinstance(next_cursor, str)
                or not next_cursor.strip()
                or next_cursor in seen_cursors
            ):
                raise NotionResponseError(
                    "Notes Data Source Queryのページネーション情報が不正です。"
                )

            seen_cursors.add(next_cursor)
            start_cursor = next_cursor

    def _ensure_schema(self) -> None:
        if not self._schema_validated:
            self.validate_schema()

    def _memo_from_page(self, page: Any) -> dict[str, Any]:
        if not isinstance(page, dict):
            raise NotionResponseError(
                "Notes Data Source Queryに不正なPageが含まれています。"
            )

        page_id = _required_text(page.get("id"), "Page ID")
        parent = page.get("parent")
        parent_data_source_id = (
            parent.get("data_source_id")
            if isinstance(parent, dict)
            else None
        )

        if (
            not isinstance(parent_data_source_id, str)
            or not _same_notion_id(
                parent_data_source_id,
                self._data_source_id,
            )
        ):
            raise NotionResponseError(
                "Notion Memoの親Data Source IDが一致しません。"
            )

        properties = page.get("properties")

        if not isinstance(properties, dict):
            raise NotionResponseError(
                "Notion Memoのpropertiesを取得できませんでした。"
            )

        note_id = _extract_integer(properties, LOCAL_ID_PROPERTY)
        content = _extract_rich_text(properties, CONTENT_PROPERTY)
        title = _extract_rich_text(properties, TITLE_PROPERTY, value_key="title")
        created_at_iso = _extract_date_start(properties, CREATED_AT_PROPERTY)
        sync_key = _extract_rich_text(properties, SYNC_KEY_PROPERTY)
        source = _extract_select_name(properties, SOURCE_PROPERTY)
        url = page.get("url")

        return {
            "id": note_id,
            "content": content,
            "created_at": _format_local_datetime(created_at_iso),
            "created_at_iso": created_at_iso,
            "sync_key": sync_key,
            "notion_page_id": page_id,
            "notion_sync_status": "synced",
            "notion_title": title,
            "notion_source": source,
            "notion_url": url.strip() if isinstance(url, str) else "",
        }


def _extract_rich_text(
    properties: dict[str, Any],
    property_name: str,
    *,
    value_key: str = "rich_text",
) -> str:
    property_value = properties.get(property_name)
    fragments = (
        property_value.get(value_key)
        if isinstance(property_value, dict)
        else None
    )

    if not isinstance(fragments, list):
        raise NotionResponseError(
            f"Notion Memoの{property_name}を取得できませんでした。"
        )

    values = []

    for fragment in fragments:
        if not isinstance(fragment, dict):
            raise NotionResponseError(
                f"Notion Memoの{property_name}が不正です。"
            )

        plain_text = fragment.get("plain_text")

        if isinstance(plain_text, str):
            values.append(plain_text)
            continue

        text = fragment.get("text")
        content = text.get("content") if isinstance(text, dict) else None

        if not isinstance(content, str):
            raise NotionResponseError(
                f"Notion Memoの{property_name}が不正です。"
            )

        values.append(content)

    return "".join(values)


def _extract_integer(
    properties: dict[str, Any],
    property_name: str,
) -> int:
    property_value = properties.get(property_name)
    number = (
        property_value.get("number")
        if isinstance(property_value, dict)
        else None
    )

    if not isinstance(number, int) or isinstance(number, bool):
        raise NotionResponseError(
            f"Notion Memoの{property_name}が整数ではありません。"
        )

    return number


def _extract_date_start(
    properties: dict[str, Any],
    property_name: str,
) -> str:
    property_value = properties.get(property_name)
    date = (
        property_value.get("date")
        if isinstance(property_value, dict)
        else None
    )
    start = date.get("start") if isinstance(date, dict) else None
    return _required_text(start, property_name)


def _extract_select_name(
    properties: dict[str, Any],
    property_name: str,
) -> str:
    property_value = properties.get(property_name)
    select = (
        property_value.get("select")
        if isinstance(property_value, dict)
        else None
    )
    name = select.get("name") if isinstance(select, dict) else None
    return _required_text(name, property_name)


def _format_local_datetime(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise NotionResponseError(
            "Notion MemoのCreated Atが有効な日時ではありません。"
        ) from None

    if parsed.tzinfo is None:
        raise NotionResponseError(
            "Notion MemoのCreated Atにタイムゾーンがありません。"
        )

    return parsed.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NotionResponseError(
            f"Notion Memoの{name}を取得できませんでした。"
        )

    return value.strip()


def _same_notion_id(first: str, second: str) -> bool:
    return _canonical_notion_id(first) == _canonical_notion_id(second)


def _canonical_notion_id(value: str) -> str:
    return value.strip().replace("-", "").lower()
