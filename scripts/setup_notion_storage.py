import argparse
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
from app.integrations.notion_memory_store import (  # noqa: E402
    MEMORY_DATA_SOURCE_SCHEMA,
    MEMORY_DATABASE_TITLE,
    NotionMemoryStore,
)
from app.integrations.notion_resources import (  # noqa: E402
    resolve_memory_data_source_id,
    resolve_tasks_data_source_id,
    save_memory_notion_resource,
    save_tasks_notion_resource,
)
from app.integrations.notion_task_store import (  # noqa: E402
    TASKS_DATA_SOURCE_SCHEMA,
    TASKS_DATABASE_TITLE,
    NotionTaskStore,
)


@dataclass(frozen=True)
class StorageSetupResult:
    entity: str
    database_id: str
    data_source_id: str
    url: str | None
    created: bool


def setup_notion_storage(
    client: NotionClient,
    *,
    entity: str,
    parent_page_id: str,
    existing_data_source_id: str | None = None,
) -> StorageSetupResult:
    normalized_parent_id = (parent_page_id or "").strip()

    if not normalized_parent_id:
        raise NotionConfigurationError(
            "NOTION_PARENT_PAGE_ID が設定されていません。"
        )

    title, schema, store_type = _entity_definition(entity)

    if existing_data_source_id:
        store = store_type(
            client=client,
            data_source_id=existing_data_source_id,
        )
        data_source = store.validate_schema()
        database_id = _extract_database_id(data_source)
        database = client.retrieve_database(database_id)
        return StorageSetupResult(
            entity=entity,
            database_id=database_id,
            data_source_id=store.data_source_id,
            url=_optional_text(database, "url"),
            created=False,
        )

    created_database = client.create_database(
        parent_page_id=normalized_parent_id,
        title=title,
        properties=schema,
        is_inline=True,
    )
    database_id = _require_text(
        created_database,
        "id",
        "Database作成レスポンスにIDがありません。",
    )
    database = client.retrieve_database(database_id)
    data_source_id = _extract_initial_data_source_id(database)
    store = store_type(
        client=client,
        data_source_id=data_source_id,
    )
    store.validate_schema()
    return StorageSetupResult(
        entity=entity,
        database_id=database_id,
        data_source_id=data_source_id,
        url=_optional_text(database, "url"),
        created=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Task / Memory用Notion Data Sourceを作成または検証します。"
    )
    parser.add_argument(
        "--entity",
        choices=("tasks", "memory", "all"),
        default="all",
    )
    arguments = parser.parse_args()
    entities = (
        ("tasks", "memory")
        if arguments.entity == "all"
        else (arguments.entity,)
    )

    try:
        client = NotionClient(
            api_token=NOTION_API_TOKEN,
            api_version=NOTION_API_VERSION,
        )
        results = []

        for entity in entities:
            existing_data_source_id = (
                resolve_tasks_data_source_id()
                if entity == "tasks"
                else resolve_memory_data_source_id()
            )
            result = setup_notion_storage(
                client,
                entity=entity,
                parent_page_id=NOTION_PARENT_PAGE_ID or "",
                existing_data_source_id=existing_data_source_id,
            )

            if entity == "tasks":
                save_tasks_notion_resource(
                    database_id=result.database_id,
                    data_source_id=result.data_source_id,
                )
            else:
                save_memory_notion_resource(
                    database_id=result.database_id,
                    data_source_id=result.data_source_id,
                )

            results.append(result)
    except NotionError as error:
        print(f"Notion Storageの設定に失敗しました: {error}", file=sys.stderr)
        return 1

    for result in results:
        action = "作成" if result.created else "検証"
        print(f"{result.entity} Data Sourceの{action}に成功しました。")
        print(f"Database ID: {result.database_id}")
        print(f"Data Source ID: {result.data_source_id}")

        if result.url:
            print(f"URL: {result.url}")

    print("Data Source IDをdata/notion_resources.jsonへ保存しました。")
    return 0


def _entity_definition(entity: str):
    if entity == "tasks":
        return (
            TASKS_DATABASE_TITLE,
            TASKS_DATA_SOURCE_SCHEMA,
            NotionTaskStore,
        )

    if entity == "memory":
        return (
            MEMORY_DATABASE_TITLE,
            MEMORY_DATA_SOURCE_SCHEMA,
            NotionMemoryStore,
        )

    raise NotionConfigurationError(f"未対応のentityです: {entity}")


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
