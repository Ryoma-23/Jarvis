import math
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


def _boolean_environment_value(
    name: str,
    *,
    default: bool = False,
) -> bool:
    value = _optional_environment_value(name)

    if value is None:
        return default

    return value.lower() in {"1", "true", "yes", "on"}


def _positive_integer_environment_value(
    name: str,
    *,
    default: int,
) -> int:
    value = _optional_environment_value(name)

    if value is None:
        return default

    try:
        parsed = int(value)
    except ValueError:
        raise ValueError(
            f"{name} は1以上の整数で設定してください。"
        ) from None

    if parsed < 1:
        raise ValueError(
            f"{name} は1以上の整数で設定してください。"
        )

    return parsed


def _bounded_float_environment_value(
    name: str,
    *,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    value = _optional_environment_value(name)

    if value is None:
        return default

    try:
        parsed = float(value)
    except ValueError:
        raise ValueError(
            f"{name} は{minimum}以上{maximum}以下の数値で設定してください。"
        ) from None

    if not math.isfinite(parsed) or not minimum <= parsed <= maximum:
        raise ValueError(
            f"{name} は{minimum}以上{maximum}以下の数値で設定してください。"
        )

    return parsed

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"

NOTES_FILE = DATA_DIR / "notes.json"
TASKS_FILE = DATA_DIR / "tasks.json"
MEMORY_FILE = DATA_DIR / "memory.json"
CONVERSATION_DB_FILE = DATA_DIR / "conversations.sqlite3"
EMBEDDINGS_DB_FILE = DATA_DIR / "embeddings.sqlite3"
CHROMA_PERSIST_DIRECTORY = DATA_DIR / "chroma"
NOTION_RESOURCES_FILE = DATA_DIR / "notion_resources.json"

PROMPTS_DIR = BASE_DIR / "prompts"

SYSTEM_PROMPT_PATH = PROMPTS_DIR / "system_prompt.txt"
NOTE_INTENT_PROMPT_PATH = PROMPTS_DIR / "note_intent_prompt.txt"
TASK_INTENT_PROMPT_PATH = PROMPTS_DIR / "task_intent_prompt.txt"
MEMORY_INTENT_PROMPT_PATH = PROMPTS_DIR / "memory_intent_prompt.txt"
ROUTER_INTENT_PROMPT_PATH = PROMPTS_DIR / "router_intent_prompt.txt"

OPENAI_API_KEY = _optional_environment_value("OPENAI_API_KEY")
OPENAI_EMBEDDING_MODEL = (
    _optional_environment_value("OPENAI_EMBEDDING_MODEL")
    or "text-embedding-3-small"
)
OPENAI_EMBEDDING_DIMENSIONS = _positive_integer_environment_value(
    "OPENAI_EMBEDDING_DIMENSIONS",
    default=1536,
)
OPENAI_EMBEDDING_BATCH_SIZE = _positive_integer_environment_value(
    "OPENAI_EMBEDDING_BATCH_SIZE",
    default=100,
)
RAG_RETRIEVAL_TOP_K = _positive_integer_environment_value(
    "RAG_RETRIEVAL_TOP_K",
    default=5,
)
RAG_RETRIEVAL_MIN_SCORE = _bounded_float_environment_value(
    "RAG_RETRIEVAL_MIN_SCORE",
    default=0.45,
    minimum=0.0,
    maximum=1.0,
)
RAG_RETRIEVAL_MAX_CONTEXT_TOKENS = _positive_integer_environment_value(
    "RAG_RETRIEVAL_MAX_CONTEXT_TOKENS",
    default=2000,
)

NOTION_API_TOKEN = _optional_environment_value("NOTION_API_TOKEN")
NOTION_PARENT_PAGE_ID = _optional_environment_value(
    "NOTION_PARENT_PAGE_ID"
)
NOTION_NOTES_DATA_SOURCE_ID = _optional_environment_value(
    "NOTION_NOTES_DATA_SOURCE_ID"
)
NOTION_TASKS_DATA_SOURCE_ID = _optional_environment_value(
    "NOTION_TASKS_DATA_SOURCE_ID"
)
NOTION_MEMORY_DATA_SOURCE_ID = _optional_environment_value(
    "NOTION_MEMORY_DATA_SOURCE_ID"
)
NOTION_NOTES_READ_ENABLED = _boolean_environment_value(
    "NOTION_NOTES_READ_ENABLED"
)
NOTION_TASKS_READ_ENABLED = _boolean_environment_value(
    "NOTION_TASKS_READ_ENABLED"
)
NOTION_MEMORY_READ_ENABLED = _boolean_environment_value(
    "NOTION_MEMORY_READ_ENABLED"
)
NOTION_API_VERSION = (
    _optional_environment_value("NOTION_API_VERSION")
    or "2026-03-11"
)
