from app.config import DATA_DIR, NOTES_FILE
from app.repositories.note_repository import build_note_repository


def get_note_repository():
    return build_note_repository(local_path=NOTES_FILE)


def init_notes_file():
    get_note_repository().load_all_local()


def load_notes():
    return get_note_repository().load_all_local()


def save_notes(notes):
    get_note_repository().save_all_local(notes)


def add_note(content):
    return get_note_repository().add(content)


def retry_pending_notion_notes():
    repository = get_note_repository()
    before = repository.load_all_local()
    attempted = sum(
        1
        for note in before
        if note.get("notion_sync_status")
        in {"pending", "delete_pending"}
    )
    repository.migrate(dry_run=False)
    after = repository.load_all_local()
    pending = sum(
        1
        for note in after
        if note.get("notion_sync_status")
        in {"pending", "delete_pending"}
    )
    return {
        "attempted": attempted,
        "synced": attempted - pending,
        "pending": pending,
    }


def format_notes_list():
    notes = get_note_repository().list()

    if not notes:
        return "まだメモはありません。"

    lines = ["現在のメモはこちらです。"]

    for note in notes:
        lines.append(
            f'{note["id"]}. {note["content"]}（{note["created_at"]}）'
        )

    return "\n".join(lines)


def search_notes(keyword):
    results = get_note_repository().search(keyword)

    if not results:
        return f"「{keyword}」に関するメモは見つかりませんでした。"

    lines = [f"「{keyword}」に関するメモはこちらです。"]

    for note in results:
        lines.append(
            f'{note["id"]}. {note["content"]}（{note["created_at"]}）'
        )

    return "\n".join(lines)


def get_note_by_local_id(note_id):
    return get_note_repository().get_by_local_id(note_id)


def get_note_by_page_id(page_id):
    return get_note_repository().get_by_page_id(page_id)


def delete_note(note_id):
    deleted = get_note_repository().delete([note_id])

    if not deleted:
        return f"{note_id}番のメモは見つかりませんでした。"

    return f"{note_id}番のメモを削除しました。"


def delete_notes(note_ids):
    deleted = get_note_repository().delete(note_ids)

    if not deleted:
        return "指定されたメモは見つかりませんでした。"

    deleted_ids = ", ".join(str(note_id) for note_id in deleted)
    return f"{deleted_ids}番のメモを削除しました。"


def delete_all_notes():
    deleted = get_note_repository().delete_all()

    if not deleted:
        return "削除するメモはありません。"

    return "すべてのメモを削除しました。"
