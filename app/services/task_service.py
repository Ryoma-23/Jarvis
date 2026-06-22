import json

from datetime import datetime

from app.config import DATA_DIR, TASKS_FILE


def init_tasks_file():
    DATA_DIR.mkdir(exist_ok=True)

    if not TASKS_FILE.exists():
        with open(TASKS_FILE, "w", encoding="utf-8") as file:
            json.dump([], file, ensure_ascii=False, indent=2)


def load_tasks():
    init_tasks_file()

    with open(TASKS_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def save_tasks(tasks):
    init_tasks_file()

    with open(TASKS_FILE, "w", encoding="utf-8") as file:
        json.dump(tasks, file, ensure_ascii=False, indent=2)


def add_task(title, due_date=None):
    tasks = load_tasks()

    next_id = 1

    if tasks:
        next_id = max(task["id"] for task in tasks) + 1

    task = {
        "id": next_id,
        "title": title,
        "status": "todo",
        "due_date": due_date,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "completed_at": None
    }

    tasks.append(task)

    save_tasks(tasks)

    return task


def format_tasks_list(status_filter="all"):
    tasks = load_tasks()

    if status_filter == "todo":
        tasks = [
            task for task in tasks
            if task["status"] == "todo"
        ]
        title = "未完了のタスクはこちらです。"

    elif status_filter == "done":
        tasks = [
            task for task in tasks
            if task["status"] == "done"
        ]
        title = "完了済みのタスクはこちらです。"

    else:
        title = "現在のタスクはこちらです。"

    if not tasks:
        return "該当するタスクはありません。"

    lines = [title]

    for task in tasks:
        status = "未完了" if task["status"] == "todo" else "完了"

        due = task["due_date"] if task["due_date"] else "期限なし"

        lines.append(
            f'{task["id"]}. {task["title"]} / {status} / 期限: {due}'
        )

    return "\n".join(lines)


def search_tasks(keyword):
    tasks = load_tasks()

    results = [
        task for task in tasks
        if keyword.lower() in task["title"].lower()
    ]

    if not results:
        return f"「{keyword}」に関するタスクは見つかりませんでした。"

    lines = [f"「{keyword}」に関するタスクはこちらです。"]

    for task in results:
        status = "未完了" if task["status"] == "todo" else "完了"

        due = task["due_date"] if task["due_date"] else "期限なし"

        lines.append(
            f'{task["id"]}. {task["title"]} / {status} / 期限: {due}'
        )

    return "\n".join(lines)


def complete_tasks(task_ids):
    tasks = load_tasks()

    completed = []

    for task in tasks:
        if task["id"] in task_ids:
            task["status"] = "done"
            task["completed_at"] = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            completed.append(task["id"])

    if not completed:
        return "指定されたタスクは見つかりませんでした。"

    save_tasks(tasks)

    ids = ", ".join(str(task_id) for task_id in completed)

    return f"{ids}番のタスクを完了にしました。"


def delete_tasks(task_ids):
    tasks = load_tasks()

    deleted = [
        task for task in tasks
        if task["id"] in task_ids
    ]

    if not deleted:
        return "指定されたタスクは見つかりませんでした。"

    new_tasks = [
        task for task in tasks
        if task["id"] not in task_ids
    ]

    save_tasks(new_tasks)

    ids = ", ".join(str(task["id"]) for task in deleted)

    return f"{ids}番のタスクを削除しました。"