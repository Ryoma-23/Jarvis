import sys

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app.services.note_service import retry_pending_notion_notes  # noqa: E402


def main() -> int:
    result = retry_pending_notion_notes()
    print(f"Retry targets: {result['attempted']}")
    print(f"Synced: {result['synced']}")
    print(f"Pending: {result['pending']}")
    return 0 if result["pending"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
