import json

from pathlib import Path
from typing import Any

from app import config
from app.integrations.notion_client import NotionConfigurationError


NOTES_DATABASE_ID_KEY = "notes_database_id"
NOTES_DATA_SOURCE_ID_KEY = "notes_data_source_id"


def resolve_notes_data_source_id() -> str | None:
    if config.NOTION_NOTES_DATA_SOURCE_ID:
        return config.NOTION_NOTES_DATA_SOURCE_ID

    resources = load_notion_resources()
    value = resources.get(NOTES_DATA_SOURCE_ID_KEY)

    if not isinstance(value, str) or not value.strip():
        return None

    return value.strip()


def load_notion_resources(
    path: Path | None = None,
) -> dict[str, Any]:
    resource_path = path or config.NOTION_RESOURCES_FILE

    if not resource_path.exists():
        return {}

    try:
        with open(resource_path, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        raise NotionConfigurationError(
            "Notionリソース設定を読み込めませんでした。"
        ) from error

    if not isinstance(data, dict):
        raise NotionConfigurationError(
            "Notionリソース設定のJSON形式が正しくありません。"
        )

    return data


def save_notes_notion_resource(
    *,
    database_id: str,
    data_source_id: str,
    path: Path | None = None,
) -> None:
    normalized_database_id = _require_identifier(
        database_id,
        "database_id",
    )
    normalized_data_source_id = _require_identifier(
        data_source_id,
        "data_source_id",
    )
    resource_path = path or config.NOTION_RESOURCES_FILE
    resources = load_notion_resources(resource_path)
    resources[NOTES_DATABASE_ID_KEY] = normalized_database_id
    resources[NOTES_DATA_SOURCE_ID_KEY] = normalized_data_source_id

    resource_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = resource_path.with_name(
        f"{resource_path.name}.tmp"
    )

    try:
        with open(temporary_path, "w", encoding="utf-8") as file:
            json.dump(resources, file, ensure_ascii=False, indent=2)
            file.write("\n")

        temporary_path.replace(resource_path)
    except OSError as error:
        raise NotionConfigurationError(
            "Notionリソース設定を保存できませんでした。"
        ) from error


def _require_identifier(value: str, name: str) -> str:
    normalized = (value or "").strip()

    if not normalized:
        raise NotionConfigurationError(
            f"{name} が指定されていません。"
        )

    return normalized
