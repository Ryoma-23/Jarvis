import os

from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


def _optional_environment_value(name: str) -> str | None:
    value = os.getenv(name)

    if value is None:
        return None

    normalized = value.strip()
    return normalized or None

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"

NOTES_FILE = DATA_DIR / "notes.json"
TASKS_FILE = DATA_DIR / "tasks.json"
MEMORY_FILE = DATA_DIR / "memory.json"
CONVERSATION_DB_FILE = DATA_DIR / "conversations.sqlite3"
NOTION_RESOURCES_FILE = DATA_DIR / "notion_resources.json"

PROMPTS_DIR = BASE_DIR / "prompts"

SYSTEM_PROMPT_PATH = PROMPTS_DIR / "system_prompt.txt"
NOTE_INTENT_PROMPT_PATH = PROMPTS_DIR / "note_intent_prompt.txt"
TASK_INTENT_PROMPT_PATH = PROMPTS_DIR / "task_intent_prompt.txt"
MEMORY_INTENT_PROMPT_PATH = PROMPTS_DIR / "memory_intent_prompt.txt"
ROUTER_INTENT_PROMPT_PATH = PROMPTS_DIR / "router_intent_prompt.txt"

NOTION_API_TOKEN = _optional_environment_value("NOTION_API_TOKEN")
NOTION_PARENT_PAGE_ID = _optional_environment_value(
    "NOTION_PARENT_PAGE_ID"
)
NOTION_NOTES_DATA_SOURCE_ID = _optional_environment_value(
    "NOTION_NOTES_DATA_SOURCE_ID"
)
NOTION_API_VERSION = (
    _optional_environment_value("NOTION_API_VERSION")
    or "2026-03-11"
)
