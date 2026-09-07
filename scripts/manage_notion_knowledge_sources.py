import argparse
import sys

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app.config import (  # noqa: E402
    CHROMA_PERSIST_DIRECTORY,
    OPENAI_EMBEDDING_DIMENSIONS,
    OPENAI_EMBEDDING_MODEL,
)
from app.knowledge_sync.registry import (  # noqa: E402
    KnowledgeSourceRegistryError,
    KnowledgeSourceRegistryStore,
)
from app.vector.chroma_index import (  # noqa: E402
    ChromaIndex,
    ChromaIndexError,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="RAGで参照する通常Notion Pageを管理します。"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="現在の参照元を表示します。")

    add_parser = subparsers.add_parser("add", help="Pageを追加します。")
    add_parser.add_argument("page_id")
    add_parser.add_argument("--label", default="")
    add_parser.add_argument("--apply", action="store_true")

    remove_parser = subparsers.add_parser(
        "remove",
        help="Pageを外します。次回Apply時にChromaから削除されます。",
    )
    remove_parser.add_argument("page_id")
    remove_parser.add_argument("--apply", action="store_true")

    notes_parser = subparsers.add_parser(
        "set-notes",
        help="Notes Data Sourceを統合同期へ含めるか設定します。",
    )
    notes_parser.add_argument("value", choices=("on", "off"))
    notes_parser.add_argument("--apply", action="store_true")

    import_parser = subparsers.add_parser(
        "import-indexed",
        help="既存Chromaの通常Pageを参照元へ取り込みます。",
    )
    import_parser.add_argument("--apply", action="store_true")
    arguments = parser.parse_args()
    store = KnowledgeSourceRegistryStore()

    try:
        registry = store.load()

        if arguments.command == "list":
            _print_registry(registry)
            return 0

        if arguments.command == "add":
            updated = registry.add_page(
                arguments.page_id,
                label=arguments.label,
            )
        elif arguments.command == "remove":
            updated = registry.remove_page(arguments.page_id)
        elif arguments.command == "set-notes":
            updated = registry.with_notes(arguments.value == "on")
        else:
            updated = _import_indexed_pages(registry)

        _print_registry(updated)

        if arguments.apply:
            store.save(updated)
            print("参照元設定を保存しました。")
        else:
            print("DRY RUN: 変更は保存していません。--applyで確定します。")

        return 0
    except (KnowledgeSourceRegistryError, ChromaIndexError) as error:
        print(f"参照元設定の操作に失敗しました: {error}", file=sys.stderr)
        return 1


def _import_indexed_pages(registry):
    index = ChromaIndex(
        model=OPENAI_EMBEDDING_MODEL,
        dimensions=OPENAI_EMBEDDING_DIMENSIONS,
        persistence_path=CHROMA_PERSIST_DIRECTORY,
        create_if_missing=False,
    )

    try:
        updated = registry

        for page in index.list_indexed_pages():
            if "notion_page" in page.source_types:
                updated = updated.add_page(page.notion_page_id)

        return updated
    finally:
        index.close()


def _print_registry(registry) -> None:
    print("Notion Knowledge Sources")
    print(f"Registry initialized: {registry.authoritative}")
    print(f"Include Notes: {registry.include_notes}")
    print(f"Normal pages: {len(registry.pages)}")

    for page in registry.pages:
        label = f" / {page.label}" if page.label else ""
        print(f"- {page.page_id}{label}")


if __name__ == "__main__":
    raise SystemExit(main())

