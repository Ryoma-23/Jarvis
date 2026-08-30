import json
import logging

from datetime import datetime
from functools import lru_cache

from app import config
from app.config import DATA_DIR, NOTES_FILE
from app.integrations.notion_client import NotionClient, NotionError
from app.integrations.notion_memo_writer import (
    NotionMemoWriter,
    build_notion_note_sync_key,
)
from app.integrations.notion_resources import (
    resolve_notes_data_source_id,
)


logger = logging.getLogger(__name__)


def init_notes_file():
    DATA_DIR.mkdir(exist_ok=True)

    if not NOTES_FILE.exists():
        with open(NOTES_FILE, "w", encoding="utf-8") as file:
            json.dump([], file, ensure_ascii=False, indent=2)


def load_notes():
    init_notes_file()

    with open(NOTES_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def save_notes(notes):
    init_notes_file()

    with open(NOTES_FILE, "w", encoding="utf-8") as file:
        json.dump(notes, file, ensure_ascii=False, indent=2)


def add_note(content):
    notes = load_notes()

    next_id = 1

    if notes:
        next_id = max(note["id"] for note in notes) + 1

    now = datetime.now().astimezone()
    created_at = now.strftime("%Y-%m-%d %H:%M:%S")
    note = {
        "id": next_id,
        "content": content,
        "created_at": created_at,
        "created_at_iso": now.isoformat(timespec="seconds"),
        "sync_key": build_notion_note_sync_key(
            note_id=next_id,
            content=content,
            created_at=created_at,
        ),
        "notion_page_id": None,
        "notion_sync_status": "pending",
    }

    notes.append(note)

    save_notes(notes)
    _sync_note_with_notion(note, notes)

    return note


def get_notion_memo_writer() -> NotionMemoWriter | None:
    data_source_id = resolve_notes_data_source_id()

    if not config.NOTION_API_TOKEN or not data_source_id:
        return None

    return _build_notion_memo_writer(
        config.NOTION_API_TOKEN,
        config.NOTION_API_VERSION,
        data_source_id,
    )


def retry_pending_notion_notes():
    notes = load_notes()
    attempted = 0
    synced = 0

    for note in notes:
        if note.get("notion_sync_status") != "pending":
            continue

        if not note.get("sync_key") or not note.get("created_at_iso"):
            continue

        attempted += 1
        _sync_note_with_notion(note, notes)

        if note.get("notion_sync_status") == "synced":
            synced += 1

    return {
        "attempted": attempted,
        "synced": synced,
        "pending": attempted - synced,
    }


@lru_cache(maxsize=1)
def _build_notion_memo_writer(
    api_token: str,
    api_version: str,
    data_source_id: str,
) -> NotionMemoWriter:
    return NotionMemoWriter(
        client=NotionClient(
            api_token=api_token,
            api_version=api_version,
        ),
        data_source_id=data_source_id,
    )


def _sync_note_with_notion(note, notes) -> None:
    try:
        writer = get_notion_memo_writer()

        if writer is None:
            return

        result = writer.sync_note(note)
    except NotionError as error:
        logger.warning(
            "Notion memo sync remains pending: note_id=%s error=%s",
            note["id"],
            error,
        )
        return
    except Exception as error:
        logger.warning(
            "Unexpected Notion memo sync failure: note_id=%s error_type=%s",
            note["id"],
            type(error).__name__,
        )
        return

    note["notion_page_id"] = result.page_id
    note["notion_sync_status"] = "synced"

    try:
        save_notes(notes)
    except Exception as error:
        logger.warning(
            "Notion memo metadata save failed: note_id=%s error_type=%s",
            note["id"],
            type(error).__name__,
        )


def format_notes_list():
    notes = load_notes()

    if not notes:
        return "まだメモはありません。"

    lines = ["現在のメモはこちらです。"]

    for note in notes:
        lines.append(
            f'{note["id"]}. {note["content"]}（{note["created_at"]}）'
        )

    return "\n".join(lines)


def search_notes(keyword):
    notes = load_notes()

    results = [
        note for note in notes
        if keyword.lower() in note["content"].lower()
    ]

    if not results:
        return f"「{keyword}」に関するメモは見つかりませんでした。"

    lines = [f"「{keyword}」に関するメモはこちらです。"]

    for note in results:
        lines.append(
            f'{note["id"]}. {note["content"]}（{note["created_at"]}）'
        )

    return "\n".join(lines)


def delete_note(note_id):
    notes = load_notes()

    new_notes = [
        note for note in notes
        if note["id"] != note_id
    ]

    if len(notes) == len(new_notes):
        return f"{note_id}番のメモは見つかりませんでした。"

    save_notes(new_notes)

    return f"{note_id}番のメモを削除しました。"


def delete_notes(note_ids):
    notes = load_notes()

    deleted_notes = [
        note for note in notes
        if note["id"] in note_ids
    ]

    if not deleted_notes:
        return "指定されたメモは見つかりませんでした。"

    new_notes = [
        note for note in notes
        if note["id"] not in note_ids
    ]

    save_notes(new_notes)

    deleted_ids = ", ".join(str(note["id"]) for note in deleted_notes)

    return f"{deleted_ids}番のメモを削除しました。"


def delete_all_notes():
    notes = load_notes()

    if not notes:
        return "削除するメモはありません。"

    save_notes([])

    return "すべてのメモを削除しました。"
