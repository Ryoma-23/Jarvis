from app.services.realtime_tools.note_tools import (
    tool_add_note,
    tool_list_notes,
    tool_search_notes,
    tool_delete_notes
)

from app.services.realtime_tools.task_tools import (
    tool_add_task,
    tool_list_tasks,
    tool_search_tasks,
    tool_complete_tasks,
    tool_delete_tasks
)

from app.services.realtime_tools.memory_tools import (
    tool_add_memory,
    tool_list_memory,
    tool_search_memory,
    tool_update_memory,
    tool_delete_memory
)


TOOL_REGISTRY = {
    # note
    "add_note": tool_add_note,
    "list_notes": tool_list_notes,
    "search_notes": tool_search_notes,
    "delete_notes": tool_delete_notes,

    # task
    "add_task": tool_add_task,
    "list_tasks": tool_list_tasks,
    "search_tasks": tool_search_tasks,
    "complete_tasks": tool_complete_tasks,
    "delete_tasks": tool_delete_tasks,

    # memory
    "add_memory": tool_add_memory,
    "list_memory": tool_list_memory,
    "search_memory": tool_search_memory,
    "update_memory": tool_update_memory,
    "delete_memory": tool_delete_memory,
}