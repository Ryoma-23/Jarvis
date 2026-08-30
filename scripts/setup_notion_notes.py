import sys

from dataclasses import dataclass
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
    NotionResponseError,
)
from app.integrations.notion_memo_writer import (  # noqa: E402
    NOTES_DATABASE_TITLE,
    NOTES_DATA_SOURCE_SCHEMA,
    NotionMemoWriter,
)
from app.integrations.notion_resources import (  # noqa: E402
    resolve_notes_data_source_id,
    save_notes_notion_resource,
)


@dataclass(frozen=True)
class NotionNotesSetupResult:
    database_id: str
    data_source_id: str
    url: str | None
    created: bool


def setup_notion_notes(
    client: NotionClient,
    *,
    parent_page_id: str,
    existing_data_source_id: str | None = None,
) -> NotionNotesSetupResult:
    normalized_parent_id = (parent_page_id or "").strip()

    if not normalized_parent_id:
        raise NotionConfigurationError(
            "NOTION_PARENT_PAGE_ID が設定されていません。"
        )

    if existing_data_source_id:
        writer = NotionMemoWriter(
            client=client,
            data_source_id=existing_data_source_id,
        )
        data_source = writer.validate_schema()
        database_id = _extract_database_id(data_source)
        database = client.retrieve_database(database_id)
        return NotionNotesSetupResult(
            database_id=database_id,
            data_source_id=writer.data_source_id,
            url=_optional_text(database, "url"),
            created=False,
        )

    created_database = client.create_database(
        parent_page_id=normalized_parent_id,
        title=NOTES_DATABASE_TITLE,
        properties=NOTES_DATA_SOURCE_SCHEMA,
        is_inline=True,
    )
    database_id = _require_text(
        created_database,
        "id",
        "Database作成レスポンスにIDがありません。",
    )
    database = client.retrieve_database(database_id)
    data_source_id = _extract_initial_data_source_id(database)
    writer = NotionMemoWriter(
        client=client,
        data_source_id=data_source_id,
    )
    writer.validate_schema()
    return NotionNotesSetupResult(
        database_id=database_id,
        data_source_id=data_source_id,
        url=_optional_text(database, "url"),
        created=True,
    )


def main() -> int:
    try:
        client = NotionClient(
            api_token=NOTION_API_TOKEN,
            api_version=NOTION_API_VERSION,
        )
        existing_data_source_id = resolve_notes_data_source_id()
        result = setup_notion_notes(
            client,
            parent_page_id=NOTION_PARENT_PAGE_ID or "",
            existing_data_source_id=existing_data_source_id,
        )
        save_notes_notion_resource(
            database_id=result.database_id,
            data_source_id=result.data_source_id,
        )
    except NotionError as error:
        print(f"Notes Data Sourceの設定に失敗しました: {error}", file=sys.stderr)
        return 1

    action = "作成" if result.created else "検証"
    print(f"Notes Data Sourceの{action}に成功しました。")
    print(f"Database ID: {result.database_id}")
    print(f"Data Source ID: {result.data_source_id}")

    if result.url:
        print(f"URL: {result.url}")

    print("Data Source IDをdata/notion_resources.jsonへ保存しました。")
    return 0


def _extract_initial_data_source_id(database: dict[str, Any]) -> str:
    data_sources = database.get("data_sources")

    if not isinstance(data_sources, list):
        raise NotionResponseError(
            "Databaseレスポンスにdata_sourcesがありません。"
        )

    for data_source in data_sources:
        if not isinstance(data_source, dict):
            continue

        data_source_id = data_source.get("id")

        if isinstance(data_source_id, str) and data_source_id.strip():
            return data_source_id.strip()

    raise NotionResponseError(
        "作成したDatabaseのInitial Data Source IDを取得できませんでした。"
    )


def _extract_database_id(data_source: dict[str, Any]) -> str:
    parent = data_source.get("parent")
    database_id = (
        parent.get("database_id")
        if isinstance(parent, dict)
        else None
    )

    if not isinstance(database_id, str) or not database_id.strip():
        raise NotionResponseError(
            "Data Sourceレスポンスに親Database IDがありません。"
        )

    return database_id.strip()


def _require_text(
    payload: dict[str, Any],
    key: str,
    error_message: str,
) -> str:
    value = payload.get(key)

    if not isinstance(value, str) or not value.strip():
        raise NotionResponseError(error_message)

    return value.strip()


def _optional_text(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


if __name__ == "__main__":
    raise SystemExit(main())
