from app.services.note_service import (
    add_note,
    format_notes_list,
    search_notes,
    delete_notes
)


def execute_realtime_tool(tool_name: str, arguments: dict):
    if tool_name == "add_note":
        content = arguments.get("content")

        if not content:
            return {
                "success": False,
                "message": "メモ内容がありません。"
            }

        note = add_note(content)

        return {
            "success": True,
            "message": f"メモしておきました。{note['id']}. {note['content']}"
        }

    if tool_name == "list_notes":
        result = format_notes_list()

        return {
            "success": True,
            "message": result
        }

    if tool_name == "search_notes":
        keyword = arguments.get("keyword")

        if not keyword:
            return {
                "success": False,
                "message": "検索キーワードがありません。"
            }

        result = search_notes(keyword)

        return {
            "success": True,
            "message": result
        }

    if tool_name == "delete_notes":
        note_ids = arguments.get("note_ids", [])

        if not note_ids:
            return {
                "success": False,
                "message": "削除するメモ番号が指定されていません。"
            }

        try:
            note_ids = [int(note_id) for note_id in note_ids]
        except ValueError:
            return {
                "success": False,
                "message": "削除するメモ番号を正しく読み取れませんでした。"
            }

        result = delete_notes(note_ids)

        return {
            "success": True,
            "message": result
        }

    return {
        "success": False,
        "message": f"未対応のtoolです: {tool_name}"
    }