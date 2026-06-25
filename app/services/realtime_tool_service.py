from app.services.note_service import (
    add_note,
    format_notes_list,
    search_notes,
    delete_notes
)

from app.services.task_service import (
    add_task,
    format_tasks_list,
    search_tasks,
    complete_tasks,
    delete_tasks
)


from app.services.memory_service import (
    add_memory,
    format_memory_list,
    search_memory,
    update_memory,
    delete_memory
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

    if tool_name == "add_task":
        title = arguments.get("title")
        due_date = arguments.get("due_date")

        if not title:
            return {
                "success": False,
                "message": "タスク名がありません。"
            }

        task = add_task(title, due_date)

        return {
            "success": True,
            "message": f"タスクを追加しました。{task['id']}. {task['title']}"
        }

    if tool_name == "list_tasks":
        status_filter = arguments.get("status_filter")
        result = format_tasks_list(status_filter=status_filter)

        return {
            "success": True,
            "message": result
        }

    if tool_name == "search_tasks":
        keyword = arguments.get("keyword")

        if not keyword:
            return {
                "success": False,
                "message": "検索キーワードがありません。"
            }

        result = search_tasks(keyword)

        return {
            "success": True,
            "message": result
        }

    if tool_name == "complete_tasks":
        task_ids = arguments.get("task_ids", [])

        if not task_ids:
            return {
                "success": False,
                "message": "完了するタスク番号が指定されていません。"
            }

        try:
            task_ids = [int(task_id) for task_id in task_ids]
        except ValueError:
            return {
                "success": False,
                "message": "完了するタスク番号を正しく読み取れませんでした。"
            }

        result = complete_tasks(task_ids)

        return {
            "success": True,
            "message": result
        }

    if tool_name == "delete_tasks":
        task_ids = arguments.get("task_ids", [])

        if not task_ids:
            return {
                "success": False,
                "message": "削除するタスク番号が指定されていません。"
            }

        try:
            task_ids = [int(task_id) for task_id in task_ids]
        except ValueError:
            return {
                "success": False,
                "message": "削除するタスク番号を正しく読み取れませんでした。"
            }

        result = delete_tasks(task_ids)

        return {
            "success": True,
            "message": result
        }
    
    if tool_name == "add_memory":
        content = arguments.get("content")
        category = arguments.get("category") or "other"

        if not content:
            return {
                "success": False,
                "message": "覚える内容がありません。"
            }

        memory = add_memory(content, category)

        return {
            "success": True,
            "message": f"覚えておきました。{memory['id']}. [{memory['category']}] {memory['content']}"
        }

    if tool_name == "list_memory":
        result = format_memory_list()

        return {
            "success": True,
            "message": result
        }

    if tool_name == "search_memory":
        keyword = arguments.get("keyword")

        if not keyword:
            return {
                "success": False,
                "message": "検索キーワードがありません。"
            }

        result = search_memory(keyword)

        return {
            "success": True,
            "message": result
        }

    if tool_name == "update_memory":
        memory_ids = arguments.get("memory_ids", [])
        content = arguments.get("content")
        category = arguments.get("category")

        if not memory_ids:
            return {
                "success": False,
                "message": "更新する記憶番号が指定されていません。"
            }

        if not content:
            return {
                "success": False,
                "message": "更新後の内容がありません。"
            }

        try:
            memory_ids = [int(memory_id) for memory_id in memory_ids]
        except ValueError:
            return {
                "success": False,
                "message": "更新する記憶番号を正しく読み取れませんでした。"
            }

        result = update_memory(memory_ids, content, category)

        return {
            "success": True,
            "message": result
        }

    if tool_name == "delete_memory":
        memory_ids = arguments.get("memory_ids", [])

        if not memory_ids:
            return {
                "success": False,
                "message": "削除する記憶番号が指定されていません。"
            }

        try:
            memory_ids = [int(memory_id) for memory_id in memory_ids]
        except ValueError:
            return {
                "success": False,
                "message": "削除する記憶番号を正しく読み取れませんでした。"
            }

        result = delete_memory(memory_ids)

        return {
            "success": True,
            "message": result
        }

    return {
        "success": False,
        "message": f"未対応のtoolです: {tool_name}"
    }