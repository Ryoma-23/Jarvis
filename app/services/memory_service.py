from app.config import DATA_DIR, MEMORY_FILE
from app.repositories.memory_repository import build_memory_repository


def get_memory_repository():
    return build_memory_repository(local_path=MEMORY_FILE)


def init_memory_file():
    get_memory_repository().load_all_local()


def load_memory():
    return get_memory_repository().load_all_local()


def save_memory(memories):
    get_memory_repository().save_all_local(memories)


def add_memory(content, category="other"):
    return get_memory_repository().add(content, category)


def format_memory_list():
    memories = get_memory_repository().list()

    if not memories:
        return "まだ覚えていることはありません。"

    lines = ["現在覚えていることはこちらです。"]

    for memory in memories:
        lines.append(
            f'{memory["id"]}. [{memory["category"]}] {memory["content"]}'
        )

    return "\n".join(lines)


def search_memory(keyword):
    results = get_memory_repository().search(keyword)

    if not results:
        return f"「{keyword}」に関する記憶は見つかりませんでした。"

    lines = [f"「{keyword}」に関する記憶はこちらです。"]

    for memory in results:
        lines.append(
            f'{memory["id"]}. [{memory["category"]}] {memory["content"]}'
        )

    return "\n".join(lines)


def delete_memory(memory_ids):
    deleted = get_memory_repository().delete(memory_ids)

    if not deleted:
        return "指定された記憶は見つかりませんでした。"

    ids = ", ".join(str(memory_id) for memory_id in deleted)
    return f"{ids}番の記憶を削除しました。"


def update_memory(memory_ids, content, category=None):
    updated = get_memory_repository().update(
        memory_ids,
        content,
        category,
    )

    if not updated:
        return "指定された記憶は見つかりませんでした。"

    ids = ", ".join(str(memory_id) for memory_id in updated)
    return f"{ids}番の記憶を更新しました。"


def format_memory_for_prompt():
    memories = get_memory_repository().list()

    if not memories:
        return "長期記憶はまだありません。"

    lines = [
        "以下はユーザーに関する長期記憶です。",
        "回答に関係がある場合のみ参考にしてください。",
    ]

    for memory in memories:
        lines.append(
            f'- [{memory["category"]}] {memory["content"]}'
        )

    return "\n".join(lines)
