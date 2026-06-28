from app.services.note_service import (
    add_note,
    format_notes_list,
    search_notes,
    delete_notes
)

from app.services.realtime_tools.common import (
    success,
    failure,
    to_int_list
)


def tool_add_note(arguments: dict):
    content = arguments.get("content")

    if not content:
        return failure("メモ内容がありません。")

    note = add_note(content)

    return success(
        f"メモしておきました。{note['id']}. {note['content']}"
    )


def tool_list_notes(arguments: dict):
    result = format_notes_list()

    return success(result)


def tool_search_notes(arguments: dict):
    keyword = arguments.get("keyword")

    if not keyword:
        return failure("検索キーワードがありません。")

    result = search_notes(keyword)

    return success(result)


def tool_delete_notes(arguments: dict):
    note_ids = arguments.get("note_ids", [])

    note_ids = to_int_list(note_ids)

    if note_ids is None:
        return failure("削除するメモ番号を正しく読み取れませんでした。")

    if not note_ids:
        return failure("削除するメモ番号が指定されていません。")

    result = delete_notes(note_ids)

    return success(result)