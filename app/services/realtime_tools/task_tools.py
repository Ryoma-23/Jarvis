from app.services.task_service import (
    add_task,
    format_tasks_list,
    search_tasks,
    complete_tasks,
    delete_tasks
)

from app.services.realtime_tools.common import (
    success,
    failure,
    to_int_list
)


def tool_add_task(arguments: dict):
    title = arguments.get("title")
    due_date = arguments.get("due_date")

    if not title:
        return failure("追加するタスク内容がありません。")

    task = add_task(title, due_date)

    due = task["due_date"] if task["due_date"] else "期限なし"

    return success(
        f"タスクに追加しました。{task['id']}. {task['title']} / 期限: {due}"
    )


def tool_list_tasks(arguments: dict):
    status_filter = arguments.get("status_filter") or "all"

    result = format_tasks_list(status_filter)

    return success(result)


def tool_search_tasks(arguments: dict):
    keyword = arguments.get("keyword")

    if not keyword:
        return failure("検索キーワードがありません。")

    result = search_tasks(keyword)

    return success(result)


def tool_complete_tasks(arguments: dict):
    task_ids = arguments.get("task_ids", [])

    task_ids = to_int_list(task_ids)

    if task_ids is None:
        return failure("完了にするタスク番号を正しく読み取れませんでした。")

    if not task_ids:
        return failure("完了にするタスク番号が指定されていません。")

    result = complete_tasks(task_ids)

    return success(result)


def tool_delete_tasks(arguments: dict):
    task_ids = arguments.get("task_ids", [])

    task_ids = to_int_list(task_ids)

    if task_ids is None:
        return failure("削除するタスク番号を正しく読み取れませんでした。")

    if not task_ids:
        return failure("削除するタスク番号が指定されていません。")

    result = delete_tasks(task_ids)

    return success(result)