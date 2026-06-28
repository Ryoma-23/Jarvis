from app.services.memory_service import (
    add_memory,
    format_memory_list,
    search_memory,
    update_memory,
    delete_memory
)

from app.services.realtime_tools.common import (
    success,
    failure,
    to_int_list
)


def tool_add_memory(arguments: dict):
    content = arguments.get("content")
    category = arguments.get("category") or "other"

    if not content:
        return failure("覚える内容がありません。")

    memory = add_memory(content, category)

    return success(
        f"覚えておきました。{memory['id']}. [{memory['category']}] {memory['content']}"
    )


def tool_list_memory(arguments: dict):
    result = format_memory_list()

    return success(result)


def tool_search_memory(arguments: dict):
    keyword = arguments.get("keyword")

    if not keyword:
        return failure("検索キーワードがありません。")

    result = search_memory(keyword)

    return success(result)


def tool_update_memory(arguments: dict):
    memory_ids = arguments.get("memory_ids", [])
    content = arguments.get("content")
    category = arguments.get("category")

    memory_ids = to_int_list(memory_ids)

    if memory_ids is None:
        return failure("更新する記憶番号を正しく読み取れませんでした。")

    if not memory_ids:
        return failure("更新する記憶番号が指定されていません。")

    if not content:
        return failure("更新後の内容がありません。")

    result = update_memory(memory_ids, content, category)

    return success(result)


def tool_delete_memory(arguments: dict):
    memory_ids = arguments.get("memory_ids", [])

    memory_ids = to_int_list(memory_ids)

    if memory_ids is None:
        return failure("削除する記憶番号を正しく読み取れませんでした。")

    if not memory_ids:
        return failure("削除する記憶番号が指定されていません。")

    result = delete_memory(memory_ids)

    return success(result)