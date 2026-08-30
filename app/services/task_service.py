from app.config import DATA_DIR, TASKS_FILE
from app.repositories.task_repository import build_task_repository


def get_task_repository():
    return build_task_repository(local_path=TASKS_FILE)


def init_tasks_file():
    get_task_repository().load_all_local()


def load_tasks():
    return get_task_repository().load_all_local()


def save_tasks(tasks):
    get_task_repository().save_all_local(tasks)


def add_task(title, due_date=None):
    return get_task_repository().add(title, due_date)


def format_tasks_list(status_filter="all"):
    tasks = get_task_repository().list(status_filter)

    if status_filter == "todo":
        title = "未完了のタスクはこちらです。"
    elif status_filter == "done":
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
    results = get_task_repository().search(keyword)

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
    completed = get_task_repository().complete(task_ids)

    if not completed:
        return "指定されたタスクは見つかりませんでした。"

    ids = ", ".join(str(task_id) for task_id in completed)
    return f"{ids}番のタスクを完了にしました。"


def delete_tasks(task_ids):
    deleted = get_task_repository().delete(task_ids)

    if not deleted:
        return "指定されたタスクは見つかりませんでした。"

    ids = ", ".join(str(task_id) for task_id in deleted)
    return f"{ids}番のタスクを削除しました。"
