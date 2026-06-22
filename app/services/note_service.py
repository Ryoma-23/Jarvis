import json

from datetime import datetime

from app.config import DATA_DIR, NOTES_FILE


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

    note = {
        "id": next_id,
        "content": content,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    notes.append(note)

    save_notes(notes)

    return note


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