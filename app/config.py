from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"

NOTES_FILE = DATA_DIR / "notes.json"
TASKS_FILE = DATA_DIR / "tasks.json"
MEMORY_FILE = DATA_DIR / "memory.json"

PROMPTS_DIR = BASE_DIR / "prompts"

SYSTEM_PROMPT_PATH = PROMPTS_DIR / "system_prompt.txt"
NOTE_INTENT_PROMPT_PATH = PROMPTS_DIR / "note_intent_prompt.txt"
TASK_INTENT_PROMPT_PATH = PROMPTS_DIR / "task_intent_prompt.txt"
MEMORY_INTENT_PROMPT_PATH = PROMPTS_DIR / "memory_intent_prompt.txt"
ROUTER_INTENT_PROMPT_PATH = PROMPTS_DIR / "router_intent_prompt.txt"