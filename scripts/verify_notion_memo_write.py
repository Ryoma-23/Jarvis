import sys

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app.config import NOTION_API_TOKEN, NOTION_API_VERSION  # noqa: E402
from app.integrations.notion_client import (  # noqa: E402
    NotionClient,
    NotionError,
)
from app.integrations.notion_memo_writer import (  # noqa: E402
    CONTENT_PROPERTY,
    LOCAL_ID_PROPERTY,
    SOURCE_PROPERTY,
    SYNC_KEY_PROPERTY,
)
from app.integrations.notion_resources import (  # noqa: E402
    resolve_notes_data_source_id,
)
from app.services.note_service import add_note, load_notes  # noqa: E402


VERIFY_MEMO_PREFIX = "JARVIS Phase 2 Notion Write Test"


class NotionMemoVerificationError(NotionError):
    """Raised when Local and Notion memo values do not match."""


@dataclass(frozen=True)
class NotionMemoVerificationResult:
    local_id: int
    notion_page_id: str
    content: str
    url: str


def verify_notion_memo_write(
    *,
    content: str,
) -> NotionMemoVerificationResult:
    data_source_id = resolve_notes_data_source_id()

    if not data_source_id:
        raise NotionMemoVerificationError(
            "Notes用Data Source IDが設定されていません。"
        )

    note = add_note(content)

    if note.get("notion_sync_status") != "synced":
        raise NotionMemoVerificationError(
            f"Local Memo {note['id']} は保存されましたが、"
            "Notion同期はpendingです。"
        )

    notion_page_id = note.get("notion_page_id")

    if not isinstance(notion_page_id, str) or not notion_page_id.strip():
        raise NotionMemoVerificationError(
            "同期済みMemoにNotion Page IDがありません。"
        )

    stored_note = next(
        (
            item
            for item in load_notes()
            if item.get("id") == note["id"]
        ),
        None,
    )

    if stored_note != note:
        raise NotionMemoVerificationError(
            "返却されたMemoとnotes.jsonのMemoが一致しません。"
        )

    client = NotionClient(
        api_token=NOTION_API_TOKEN,
        api_version=NOTION_API_VERSION,
    )
    page = client.retrieve_page(notion_page_id)
    parent = page.get("parent")
    actual_data_source_id = (
        parent.get("data_source_id")
        if isinstance(parent, dict)
        else None
    )

    if not isinstance(actual_data_source_id, str) or not _same_notion_id(
        actual_data_source_id,
        data_source_id,
    ):
        raise NotionMemoVerificationError(
            "作成したMemoのData Source IDが一致しません。"
        )

    properties = page.get("properties")

    if not isinstance(properties, dict):
        raise NotionMemoVerificationError(
            "Notion Memoのpropertiesを取得できません。"
        )

    if _extract_rich_text(properties, CONTENT_PROPERTY) != content:
        raise NotionMemoVerificationError(
            "LocalとNotionのContentが一致しません。"
        )

    local_id_property = properties.get(LOCAL_ID_PROPERTY)
    notion_local_id = (
        local_id_property.get("number")
        if isinstance(local_id_property, dict)
        else None
    )

    if notion_local_id != note["id"]:
        raise NotionMemoVerificationError(
            "LocalとNotionのJarvis Local IDが一致しません。"
        )

    if _extract_rich_text(
        properties,
        SYNC_KEY_PROPERTY,
    ) != note["sync_key"]:
        raise NotionMemoVerificationError(
            "LocalとNotionのSync Keyが一致しません。"
        )

    source_property = properties.get(SOURCE_PROPERTY)
    source = (
        source_property.get("select")
        if isinstance(source_property, dict)
        else None
    )
    source_name = source.get("name") if isinstance(source, dict) else None

    if source_name != "JARVIS":
        raise NotionMemoVerificationError(
            "Notion MemoのSourceがJARVISではありません。"
        )

    url = page.get("url")

    if not isinstance(url, str) or not url.strip():
        raise NotionMemoVerificationError(
            "Notion MemoのURLを取得できません。"
        )

    return NotionMemoVerificationResult(
        local_id=note["id"],
        notion_page_id=notion_page_id,
        content=content,
        url=url.strip(),
    )


def main() -> int:
    content = (
        f"{VERIFY_MEMO_PREFIX} - "
        f"{datetime.now().astimezone().isoformat(timespec='seconds')}"
    )

    try:
        result = verify_notion_memo_write(content=content)
    except NotionError as error:
        print(f"Memo Dual Writeの確認に失敗しました: {error}", file=sys.stderr)
        return 1

    print("Memo Dual Writeの確認に成功しました。")
    print(f"Local ID: {result.local_id}")
    print(f"Notion Page ID: {result.notion_page_id}")
    print(f"Content: {result.content}")
    print(f"URL: {result.url}")
    print("確認用Memoはnotes.jsonとNotionの両方に残しています。")
    return 0


def _extract_rich_text(
    properties: dict[str, Any],
    property_name: str,
) -> str:
    property_value = properties.get(property_name)
    fragments = (
        property_value.get("rich_text")
        if isinstance(property_value, dict)
        else None
    )

    if not isinstance(fragments, list):
        raise NotionMemoVerificationError(
            f"Notion Memoの{property_name}を取得できません。"
        )

    return "".join(
        item.get("plain_text", "")
        for item in fragments
        if isinstance(item, dict)
    )


def _same_notion_id(first: str, second: str) -> bool:
    return _canonical_notion_id(first) == _canonical_notion_id(second)


def _canonical_notion_id(value: str) -> str:
    return value.strip().replace("-", "").lower()


if __name__ == "__main__":
    raise SystemExit(main())
