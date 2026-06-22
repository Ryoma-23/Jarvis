import json

from datetime import datetime

from app.config import DATA_DIR, MEMORY_FILE


def init_memory_file():
    DATA_DIR.mkdir(exist_ok=True)

    if not MEMORY_FILE.exists():
        with open(MEMORY_FILE, "w", encoding="utf-8") as file:
            json.dump([], file, ensure_ascii=False, indent=2)


def load_memory():
    init_memory_file()

    with open(MEMORY_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def save_memory(memories):
    init_memory_file()

    with open(MEMORY_FILE, "w", encoding="utf-8") as file:
        json.dump(memories, file, ensure_ascii=False, indent=2)


def add_memory(content, category="other"):
    memories = load_memory()

    next_id = 1

    if memories:
        next_id = max(memory["id"] for memory in memories) + 1

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    memory = {
        "id": next_id,
        "content": content,
        "category": category or "other",
        "created_at": now,
        "updated_at": now
    }

    memories.append(memory)

    save_memory(memories)

    return memory


def format_memory_list():
    memories = load_memory()

    if not memories:
        return "まだ覚えていることはありません。"

    lines = ["現在覚えていることはこちらです。"]

    for memory in memories:
        lines.append(
            f'{memory["id"]}. [{memory["category"]}] {memory["content"]}'
        )

    return "\n".join(lines)


def search_memory(keyword):
    memories = load_memory()

    results = [
        memory for memory in memories
        if keyword.lower() in memory["content"].lower()
        or keyword.lower() in memory["category"].lower()
    ]

    if not results:
        return f"「{keyword}」に関する記憶は見つかりませんでした。"

    lines = [f"「{keyword}」に関する記憶はこちらです。"]

    for memory in results:
        lines.append(
            f'{memory["id"]}. [{memory["category"]}] {memory["content"]}'
        )

    return "\n".join(lines)


def delete_memory(memory_ids):
    memories = load_memory()

    deleted = [
        memory for memory in memories
        if memory["id"] in memory_ids
    ]

    if not deleted:
        return "指定された記憶は見つかりませんでした。"

    new_memories = [
        memory for memory in memories
        if memory["id"] not in memory_ids
    ]

    save_memory(new_memories)

    ids = ", ".join(str(memory["id"]) for memory in deleted)

    return f"{ids}番の記憶を削除しました。"


def update_memory(memory_ids, content, category=None):
    memories = load_memory()

    updated = []

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for memory in memories:
        if memory["id"] in memory_ids:
            memory["content"] = content

            if category:
                memory["category"] = category

            memory["updated_at"] = now

            updated.append(memory["id"])

    if not updated:
        return "指定された記憶は見つかりませんでした。"

    save_memory(memories)

    ids = ", ".join(str(memory_id) for memory_id in updated)

    return f"{ids}番の記憶を更新しました。"


def format_memory_for_prompt():
    memories = load_memory()

    if not memories:
        return "長期記憶はまだありません。"

    lines = [
        "以下はユーザーに関する長期記憶です。",
        "回答に関係がある場合のみ参考にしてください。"
    ]

    for memory in memories:
        lines.append(
            f'- [{memory["category"]}] {memory["content"]}'
        )

    return "\n".join(lines)