import hashlib

from dataclasses import dataclass
from typing import Any

from app.integrations.notion_client import (
    NotionClient,
    NotionConfigurationError,
    NotionResponseError,
)


NOTES_DATABASE_TITLE = "JARVIS Notes"
NOTES_SOURCE_NAME = "JARVIS"
NOTION_RICH_TEXT_FRAGMENT_LIMIT = 2000
NOTION_NOTE_TITLE_LIMIT = 100

TITLE_PROPERTY = "Title"
CONTENT_PROPERTY = "Content"
LOCAL_ID_PROPERTY = "Jarvis Local ID"
CREATED_AT_PROPERTY = "Created At"
SOURCE_PROPERTY = "Source"
SYNC_KEY_PROPERTY = "Sync Key"

NOTES_DATA_SOURCE_SCHEMA = {
    TITLE_PROPERTY: {"title": {}},
    CONTENT_PROPERTY: {"rich_text": {}},
    LOCAL_ID_PROPERTY: {"number": {"format": "number"}},
    CREATED_AT_PROPERTY: {"date": {}},
    SOURCE_PROPERTY: {
        "select": {
            "options": [
                {
                    "name": NOTES_SOURCE_NAME,
                    "color": "blue",
                }
            ]
        }
    },
    SYNC_KEY_PROPERTY: {"rich_text": {}},
}

REQUIRED_NOTES_PROPERTY_TYPES = {
    TITLE_PROPERTY: "title",
    CONTENT_PROPERTY: "rich_text",
    LOCAL_ID_PROPERTY: "number",
    CREATED_AT_PROPERTY: "date",
    SOURCE_PROPERTY: "select",
    SYNC_KEY_PROPERTY: "rich_text",
}


@dataclass(frozen=True)
class NotionMemoSyncResult:
    page_id: str
    already_existed: bool


class NotionMemoWriter:
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

    def sync_note(self, note: dict[str, Any]) -> NotionMemoSyncResult:
        if not self._schema_validated:
            self.validate_schema()

        note_id = _require_note_integer(note, "id")
        content = _require_note_text(note, "content")
        created_at_iso = _require_note_text(note, "created_at_iso")
        sync_key = _require_note_text(note, "sync_key")
        existing_page_id = self.find_page_id_by_sync_key(sync_key)

        if existing_page_id is not None:
            return NotionMemoSyncResult(
                page_id=existing_page_id,
                already_existed=True,
            )

        page = self._client.create_data_source_page(
            data_source_id=self._data_source_id,
            properties={
                TITLE_PROPERTY: {
                    "title": _rich_text_fragments(
                        _build_title(content),
                    )
                },
                CONTENT_PROPERTY: {
                    "rich_text": _rich_text_fragments(content)
                },
                LOCAL_ID_PROPERTY: {"number": note_id},
                CREATED_AT_PROPERTY: {
                    "date": {"start": created_at_iso}
                },
                SOURCE_PROPERTY: {
                    "select": {"name": NOTES_SOURCE_NAME}
                },
                SYNC_KEY_PROPERTY: {
                    "rich_text": _rich_text_fragments(sync_key)
                },
            },
        )
        page_id = page.get("id")

        if not isinstance(page_id, str) or not page_id.strip():
            raise NotionResponseError(
                "NotionのMemo作成レスポンスにPage IDがありません。"
            )

        return NotionMemoSyncResult(
            page_id=page_id.strip(),
            already_existed=False,
        )

    def find_page_id_by_sync_key(self, sync_key: str) -> str | None:
        normalized_sync_key = (sync_key or "").strip()

        if not normalized_sync_key:
            raise NotionConfigurationError(
                "MemoのSync Keyが指定されていません。"
            )

        response = self._client.query_data_source(
            self._data_source_id,
            filter_body={
                "property": SYNC_KEY_PROPERTY,
                "rich_text": {"equals": normalized_sync_key},
            },
            page_size=100,
        )
        results = response.get("results")

        if not isinstance(results, list):
            raise NotionResponseError(
                "Notes Data Source Queryのresultsを取得できませんでした。"
            )

        for page in results:
            page_id = page.get("id") if isinstance(page, dict) else None

            if isinstance(page_id, str) and page_id.strip():
                return page_id.strip()

        return None

    def trash_page(self, page_id: str) -> dict[str, Any]:
        if not self._schema_validated:
            self.validate_schema()

        return self._client.update_page(page_id, in_trash=True)


def build_notion_note_sync_key(
    *,
    note_id: int,
    content: str,
    created_at: str,
) -> str:
    source = f"{note_id}\0{created_at}\0{content}".encode("utf-8")
    digest = hashlib.sha256(source).hexdigest()
    return f"jarvis-note:{note_id}:{digest}"


def validate_notes_data_source_schema(
    client: NotionClient,
    data_source_id: str,
) -> dict[str, Any]:
    data_source = client.retrieve_data_source(data_source_id)
    properties = data_source.get("properties")

    if not isinstance(properties, dict):
        raise NotionResponseError(
            "Notes Data Sourceのpropertiesを取得できませんでした。"
        )

    mismatches = []

    for name, expected_type in REQUIRED_NOTES_PROPERTY_TYPES.items():
        property_schema = properties.get(name)
        actual_type = (
            property_schema.get("type")
            if isinstance(property_schema, dict)
            else None
        )

        if actual_type != expected_type:
            mismatches.append(
                f"{name}: expected={expected_type}, actual={actual_type}"
            )

    if mismatches:
        raise NotionConfigurationError(
            "Notes Data Sourceのスキーマが一致しません: "
            + "; ".join(mismatches)
        )

    return data_source


def _build_title(content: str) -> str:
    single_line = " ".join(content.split())

    if not single_line:
        return "Untitled Memo"

    return single_line[:NOTION_NOTE_TITLE_LIMIT]


def _rich_text_fragments(value: str) -> list[dict[str, Any]]:
    return [
        {
            "type": "text",
            "text": {"content": value[index:index + NOTION_RICH_TEXT_FRAGMENT_LIMIT]},
        }
        for index in range(0, len(value), NOTION_RICH_TEXT_FRAGMENT_LIMIT)
    ]


def _require_note_text(note: dict[str, Any], name: str) -> str:
    value = note.get(name)

    if not isinstance(value, str) or not value.strip():
        raise NotionConfigurationError(
            f"Memoの{name}が設定されていません。"
        )

    return value


def _require_note_integer(note: dict[str, Any], name: str) -> int:
    value = note.get(name)

    if not isinstance(value, int):
        raise NotionConfigurationError(
            f"Memoの{name}が整数ではありません。"
        )

    return value
