import sys

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app.config import NOTION_API_TOKEN, NOTION_API_VERSION  # noqa: E402
from app.integrations.notion_client import (  # noqa: E402
    NotionClient,
    NotionError,
)
from app.integrations.notion_memo_reader import (  # noqa: E402
    NotionMemoReader,
)
from app.integrations.notion_resources import (  # noqa: E402
    resolve_notes_data_source_id,
)
from app.services.note_service import load_notes  # noqa: E402


class NotionMemoReadVerificationError(NotionError):
    """Raised when structured Notion reads do not match synced Local Memo."""


@dataclass(frozen=True)
class NotionMemoReadVerificationResult:
    local_synced_count: int
    notion_count: int
    matched_count: int
    untracked_notion_count: int
    verified_local_id: int
    verified_page_id: str
    verified_url: str


def verify_notion_memo_read() -> NotionMemoReadVerificationResult:
    data_source_id = resolve_notes_data_source_id()

    if not data_source_id:
        raise NotionMemoReadVerificationError(
            "Notes用Data Source IDが設定されていません。"
        )

    reader = NotionMemoReader(
        client=NotionClient(
            api_token=NOTION_API_TOKEN,
            api_version=NOTION_API_VERSION,
        ),
        data_source_id=data_source_id,
    )
    local_notes = [
        note
        for note in load_notes()
        if note.get("notion_sync_status") == "synced"
        and isinstance(note.get("notion_page_id"), str)
    ]

    if not local_notes:
        raise NotionMemoReadVerificationError(
            "比較対象となるNotion同期済みLocal Memoがありません。"
        )

    notion_notes = reader.list_notes()
    _verify_created_at_order(notion_notes)

    local_by_page_id = _index_by_page_id(local_notes, "Local")
    notion_by_page_id = _index_by_page_id(notion_notes, "Notion")
    matched_page_ids = local_by_page_id.keys() & notion_by_page_id.keys()

    if len(matched_page_ids) != len(local_notes):
        raise NotionMemoReadVerificationError(
            "Localが追跡する同期済みPageをNotionからすべて取得できませんでした: "
            f"local={len(local_notes)}, matched={len(matched_page_ids)}"
        )

    for canonical_page_id in matched_page_ids:
        _verify_major_fields(
            local_by_page_id[canonical_page_id],
            notion_by_page_id[canonical_page_id],
        )

    verification_local = local_notes[0]
    local_id = verification_local["id"]
    content = verification_local.get("content")
    page_id = verification_local["notion_page_id"]

    if not isinstance(content, str) or not content:
        raise NotionMemoReadVerificationError(
            f"Local Memo {local_id} のContentが空です。"
        )

    by_local_id_results = reader.find_by_local_id(local_id)
    by_local_id = next(
        (
            note
            for note in by_local_id_results
            if _same_notion_id(note.get("notion_page_id"), page_id)
        ),
        None,
    )

    if by_local_id is None:
        raise NotionMemoReadVerificationError(
            f"Local ID {local_id} でNotion Memoを取得できませんでした。"
        )

    _verify_major_fields(verification_local, by_local_id)

    keyword = content[:100]
    content_results = reader.search_content(keyword)

    if not any(note.get("id") == local_id for note in content_results):
        raise NotionMemoReadVerificationError(
            "Content部分一致検索で対象Memoを取得できませんでした。"
        )

    by_page_id = reader.get_by_page_id(page_id)
    _verify_major_fields(verification_local, by_page_id)
    verified_url = by_page_id.get("notion_url")

    if not isinstance(verified_url, str) or not verified_url:
        raise NotionMemoReadVerificationError(
            "Page ID取得結果にNotion URLがありません。"
        )

    return NotionMemoReadVerificationResult(
        local_synced_count=len(local_notes),
        notion_count=len(notion_notes),
        matched_count=len(matched_page_ids),
        untracked_notion_count=len(notion_notes) - len(matched_page_ids),
        verified_local_id=local_id,
        verified_page_id=page_id,
        verified_url=verified_url,
    )


def _verify_created_at_order(notes):
    created_values = [
        _parse_datetime(note.get("created_at_iso"), "Notion Created At")
        for note in notes
    ]

    if created_values != sorted(created_values):
        raise NotionMemoReadVerificationError(
            "Notion MemoがCreated At昇順で返されませんでした。"
        )


def _index_by_page_id(notes, source):
    indexed = {}

    for note in notes:
        page_id = note.get("notion_page_id")

        if not isinstance(page_id, str) or not page_id.strip():
            raise NotionMemoReadVerificationError(
                f"{source} MemoにPage IDがありません。"
            )

        canonical_page_id = _canonical_notion_id(page_id)

        if canonical_page_id in indexed:
            raise NotionMemoReadVerificationError(
                f"{source} MemoのPage ID {page_id} が重複しています。"
            )

        indexed[canonical_page_id] = note

    return indexed


def _verify_major_fields(local_note, notion_note):
    note_id = local_note["id"]

    for field in ("id", "content", "sync_key"):
        if local_note.get(field) != notion_note.get(field):
            raise NotionMemoReadVerificationError(
                f"Memo {note_id} の{field}がLocalとNotionで一致しません。"
            )

    if not _same_notion_id(
        local_note.get("notion_page_id"),
        notion_note.get("notion_page_id"),
    ):
        raise NotionMemoReadVerificationError(
            f"Memo {note_id} のPage IDがLocalとNotionで一致しません。"
        )

    local_created_at = _parse_datetime(
        local_note.get("created_at_iso"),
        "Local Created At",
    )
    notion_created_at = _parse_datetime(
        notion_note.get("created_at_iso"),
        "Notion Created At",
    )

    if (
        local_created_at.replace(second=0, microsecond=0)
        != notion_created_at.replace(second=0, microsecond=0)
    ):
        raise NotionMemoReadVerificationError(
            f"Memo {note_id} のCreated Atが分単位で一致しません。"
        )


def _parse_datetime(value, name):
    if not isinstance(value, str):
        raise NotionMemoReadVerificationError(
            f"{name}を取得できませんでした。"
        )

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise NotionMemoReadVerificationError(
            f"{name}が有効な日時ではありません。"
        ) from None

    if parsed.tzinfo is None:
        raise NotionMemoReadVerificationError(
            f"{name}にタイムゾーンがありません。"
        )

    return parsed


def _same_notion_id(first, second):
    return (
        isinstance(first, str)
        and isinstance(second, str)
        and _canonical_notion_id(first) == _canonical_notion_id(second)
    )


def _canonical_notion_id(value):
    return value.strip().replace("-", "").lower()


def main() -> int:
    try:
        result = verify_notion_memo_read()
    except NotionError as error:
        print(f"Memo Structured Readの確認に失敗しました: {error}", file=sys.stderr)
        return 1

    print("Memo Structured Readの確認に成功しました。")
    print(f"Local synced count: {result.local_synced_count}")
    print(f"Notion count: {result.notion_count}")
    print(f"Tracked match count: {result.matched_count}")
    print(f"Untracked Notion count: {result.untracked_notion_count}")
    print(f"Verified Local ID: {result.verified_local_id}")
    print(f"Verified Page ID: {result.verified_page_id}")
    print(f"URL: {result.verified_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
