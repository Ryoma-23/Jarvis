from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.integrations.notion_client import (
    NotionClient,
    NotionConfigurationError,
    NotionResponseError,
)


NOTION_QUERY_PAGE_SIZE = 100
NOTION_RICH_TEXT_FRAGMENT_LIMIT = 2000


@dataclass(frozen=True)
class NotionRecordSyncResult:
    page_id: str
    already_existed: bool


class BaseNotionDataSourceStore:
    def __init__(
        self,
        *,
        client: NotionClient,
        data_source_id: str,
        required_property_types: dict[str, str],
    ):
        normalized_data_source_id = (data_source_id or "").strip()

        if not normalized_data_source_id:
            raise NotionConfigurationError(
                "Data Source IDが設定されていません。"
            )

        self.client = client
        self.data_source_id = normalized_data_source_id
        self.required_property_types = dict(required_property_types)
        self._schema_validated = False

    def validate_schema(self) -> dict[str, Any]:
        data_source = self.client.retrieve_data_source(
            self.data_source_id
        )
        properties = data_source.get("properties")

        if not isinstance(properties, dict):
            raise NotionResponseError(
                "Data Sourceのpropertiesを取得できませんでした。"
            )

        mismatches = []

        for name, expected_type in self.required_property_types.items():
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
                "Data Sourceのスキーマが一致しません: "
                + "; ".join(mismatches)
            )

        self._schema_validated = True
        return data_source

    def query_pages(
        self,
        *,
        filter_body: dict[str, Any] | None = None,
        sorts: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        self._ensure_schema()
        pages = []
        start_cursor = None
        seen_cursors = set()

        while True:
            response = self.client.query_data_source(
                self.data_source_id,
                filter_body=filter_body,
                sorts=sorts,
                start_cursor=start_cursor,
                page_size=NOTION_QUERY_PAGE_SIZE,
            )
            results = response.get("results")
            has_more = response.get("has_more")

            if not isinstance(results, list):
                raise NotionResponseError(
                    "Data Source Queryのresultsを取得できませんでした。"
                )

            if not isinstance(has_more, bool):
                raise NotionResponseError(
                    "Data Source Queryのhas_moreを取得できませんでした。"
                )

            for page in results:
                if not isinstance(page, dict):
                    raise NotionResponseError(
                        "Data Source Queryに不正なPageが含まれています。"
                    )

                validate_page_parent(page, self.data_source_id)
                pages.append(page)

            if not has_more:
                return pages

            next_cursor = response.get("next_cursor")

            if (
                not isinstance(next_cursor, str)
                or not next_cursor.strip()
                or next_cursor in seen_cursors
            ):
                raise NotionResponseError(
                    "Data Source Queryのページネーション情報が不正です。"
                )

            seen_cursors.add(next_cursor)
            start_cursor = next_cursor

    def find_by_rich_text(
        self,
        property_name: str,
        value: str,
        *,
        condition: str = "equals",
    ) -> list[dict[str, Any]]:
        normalized = require_text(value, property_name)
        return self.query_pages(
            filter_body={
                "property": property_name,
                "rich_text": {condition: normalized},
            }
        )

    def find_by_number(
        self,
        property_name: str,
        value: int,
    ) -> list[dict[str, Any]]:
        if not isinstance(value, int) or isinstance(value, bool):
            raise NotionConfigurationError(
                f"{property_name}は整数で指定してください。"
            )

        return self.query_pages(
            filter_body={
                "property": property_name,
                "number": {"equals": value},
            }
        )

    def retrieve_page(self, page_id: str) -> dict[str, Any]:
        self._ensure_schema()
        page = self.client.retrieve_page(page_id)
        validate_page_parent(page, self.data_source_id)
        return page

    def create_page(
        self,
        properties: dict[str, Any],
    ) -> dict[str, Any]:
        self._ensure_schema()
        return self.client.create_data_source_page(
            data_source_id=self.data_source_id,
            properties=properties,
        )

    def update_page(
        self,
        page_id: str,
        properties: dict[str, Any],
    ) -> dict[str, Any]:
        self._ensure_schema()
        return self.client.update_page(
            page_id,
            properties=properties,
        )

    def trash_page(self, page_id: str) -> dict[str, Any]:
        self._ensure_schema()
        return self.client.update_page(page_id, in_trash=True)

    def _ensure_schema(self) -> None:
        if not self._schema_validated:
            self.validate_schema()


def rich_text_fragments(value: str) -> list[dict[str, Any]]:
    normalized = require_text(value, "text")
    return [
        {
            "type": "text",
            "text": {
                "content": normalized[
                    index:index + NOTION_RICH_TEXT_FRAGMENT_LIMIT
                ]
            },
        }
        for index in range(
            0,
            len(normalized),
            NOTION_RICH_TEXT_FRAGMENT_LIMIT,
        )
    ]


def extract_rich_text(
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
            f"Pageの{property_name}を取得できませんでした。"
        )

    values = []

    for fragment in fragments:
        if not isinstance(fragment, dict):
            raise NotionResponseError(
                f"Pageの{property_name}が不正です。"
            )

        plain_text = fragment.get("plain_text")

        if isinstance(plain_text, str):
            values.append(plain_text)
            continue

        text = fragment.get("text")
        content = text.get("content") if isinstance(text, dict) else None

        if not isinstance(content, str):
            raise NotionResponseError(
                f"Pageの{property_name}が不正です。"
            )

        values.append(content)

    return "".join(values)


def extract_number(
    properties: dict[str, Any],
    property_name: str,
) -> int:
    property_value = properties.get(property_name)
    number = (
        property_value.get("number")
        if isinstance(property_value, dict)
        else None
    )

    if (
        isinstance(number, float)
        and number.is_integer()
    ):
        number = int(number)

    if not isinstance(number, int) or isinstance(number, bool):
        raise NotionResponseError(
            f"Pageの{property_name}が整数ではありません。"
        )

    return number


def extract_date(
    properties: dict[str, Any],
    property_name: str,
    *,
    required: bool = False,
) -> str | None:
    property_value = properties.get(property_name)
    date = (
        property_value.get("date")
        if isinstance(property_value, dict)
        else None
    )

    if date is None and not required:
        return None

    start = date.get("start") if isinstance(date, dict) else None

    if not isinstance(start, str) or not start.strip():
        raise NotionResponseError(
            f"Pageの{property_name}を取得できませんでした。"
        )

    return start.strip()


def extract_select(
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
    return require_response_text(name, property_name)


def extract_status(
    properties: dict[str, Any],
    property_name: str,
) -> str:
    property_value = properties.get(property_name)
    status = (
        property_value.get("status")
        if isinstance(property_value, dict)
        else None
    )
    name = status.get("name") if isinstance(status, dict) else None
    return require_response_text(name, property_name)


def page_properties(page: dict[str, Any]) -> dict[str, Any]:
    properties = page.get("properties")

    if not isinstance(properties, dict):
        raise NotionResponseError(
            "Pageのpropertiesを取得できませんでした。"
        )

    return properties


def page_id(page: dict[str, Any]) -> str:
    return require_response_text(page.get("id"), "Page ID")


def page_url(page: dict[str, Any]) -> str:
    value = page.get("url")
    return value.strip() if isinstance(value, str) else ""


def validate_page_parent(
    page: dict[str, Any],
    data_source_id: str,
) -> None:
    parent = page.get("parent")
    actual_id = (
        parent.get("data_source_id")
        if isinstance(parent, dict)
        else None
    )

    if (
        not isinstance(actual_id, str)
        or canonical_notion_id(actual_id)
        != canonical_notion_id(data_source_id)
    ):
        raise NotionResponseError(
            "Pageの親Data Source IDが一致しません。"
        )


def format_local_datetime(value: str) -> str:
    return parse_iso_datetime(value).astimezone().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def local_datetime_to_iso(value: str) -> str:
    normalized = require_text(value, "datetime")

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        raise NotionConfigurationError(
            f"日時の形式が正しくありません: {normalized}"
        ) from None

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=datetime.now().astimezone().tzinfo
        )

    return parsed.isoformat(timespec="seconds")


def parse_iso_datetime(value: str) -> datetime:
    normalized = require_response_text(value, "date")

    try:
        parsed = datetime.fromisoformat(
            normalized.replace("Z", "+00:00")
        )
    except ValueError:
        raise NotionResponseError(
            "Pageの日時が有効なISO形式ではありません。"
        ) from None

    if parsed.tzinfo is None:
        raise NotionResponseError(
            "Pageの日時にタイムゾーンがありません。"
        )

    return parsed


def require_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NotionConfigurationError(
            f"{name} が指定されていません。"
        )

    return value.strip()


def require_response_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NotionResponseError(
            f"Pageの{name}を取得できませんでした。"
        )

    return value.strip()


def canonical_notion_id(value: str) -> str:
    return value.strip().replace("-", "").lower()
