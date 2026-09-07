import json

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import NOTION_KNOWLEDGE_SOURCES_FILE


REGISTRY_VERSION = 1


class KnowledgeSourceRegistryError(RuntimeError):
    """Raised when the local Notion knowledge-source registry is invalid."""


@dataclass(frozen=True)
class KnowledgePageSource:
    page_id: str
    label: str = ""

    @property
    def page_key(self) -> str:
        return canonical_notion_id(self.page_id)


@dataclass(frozen=True)
class KnowledgeSourceRegistry:
    pages: tuple[KnowledgePageSource, ...] = ()
    include_notes: bool = True
    authoritative: bool = False

    def add_page(
        self,
        page_id: str,
        *,
        label: str = "",
    ) -> "KnowledgeSourceRegistry":
        source = KnowledgePageSource(
            page_id=_required_text(page_id, "Notion Page ID"),
            label=(label or "").strip(),
        )
        pages = {
            page.page_key: page
            for page in self.pages
        }
        existing = pages.get(source.page_key)

        if existing is not None and not source.label:
            source = KnowledgePageSource(
                page_id=source.page_id,
                label=existing.label,
            )

        pages[source.page_key] = source
        return KnowledgeSourceRegistry(
            pages=tuple(pages[key] for key in sorted(pages)),
            include_notes=self.include_notes,
            authoritative=True,
        )

    def remove_page(self, page_id: str) -> "KnowledgeSourceRegistry":
        page_key = canonical_notion_id(page_id)
        return KnowledgeSourceRegistry(
            pages=tuple(
                page for page in self.pages
                if page.page_key != page_key
            ),
            include_notes=self.include_notes,
            authoritative=True,
        )

    def with_notes(self, enabled: bool) -> "KnowledgeSourceRegistry":
        return KnowledgeSourceRegistry(
            pages=self.pages,
            include_notes=bool(enabled),
            authoritative=True,
        )


class KnowledgeSourceRegistryStore:
    def __init__(
        self,
        path: str | Path = NOTION_KNOWLEDGE_SOURCES_FILE,
    ):
        self.path = Path(path)

    def load(self) -> KnowledgeSourceRegistry:
        if not self.path.exists():
            return KnowledgeSourceRegistry()

        try:
            with open(self.path, "r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError) as error:
            raise KnowledgeSourceRegistryError(
                "Notion参照ページ設定を読み込めませんでした。"
            ) from error

        return _registry_from_json(data)

    def save(self, registry: KnowledgeSourceRegistry) -> None:
        data = {
            "version": REGISTRY_VERSION,
            "include_notes": registry.include_notes,
            "pages": [
                {
                    "page_id": page.page_id,
                    "label": page.label,
                }
                for page in registry.pages
            ],
        }
        _atomic_json_write(
            path=self.path,
            data=data,
            error_message="Notion参照ページ設定を保存できませんでした。",
        )


def canonical_notion_id(value: str) -> str:
    normalized = _required_text(value, "Notion Page ID")
    return normalized.replace("-", "").lower()


def _registry_from_json(data: Any) -> KnowledgeSourceRegistry:
    if not isinstance(data, dict) or data.get("version") != REGISTRY_VERSION:
        raise KnowledgeSourceRegistryError(
            "Notion参照ページ設定のversionが不正です。"
        )

    include_notes = data.get("include_notes", True)
    raw_pages = data.get("pages")

    if not isinstance(include_notes, bool) or not isinstance(raw_pages, list):
        raise KnowledgeSourceRegistryError(
            "Notion参照ページ設定のJSON形式が不正です。"
        )

    pages: dict[str, KnowledgePageSource] = {}

    for raw_page in raw_pages:
        if not isinstance(raw_page, dict):
            raise KnowledgeSourceRegistryError(
                "Notion参照ページ設定に不正なPageが含まれています。"
            )

        page_id = raw_page.get("page_id")
        label = raw_page.get("label", "")

        if not isinstance(page_id, str) or not isinstance(label, str):
            raise KnowledgeSourceRegistryError(
                "Notion参照ページ設定のPage IDまたはlabelが不正です。"
            )

        source = KnowledgePageSource(
            page_id=_required_text(page_id, "Notion Page ID"),
            label=label.strip(),
        )

        if source.page_key in pages:
            raise KnowledgeSourceRegistryError(
                "Notion参照ページ設定に同じPage IDが重複しています。"
            )

        pages[source.page_key] = source

    return KnowledgeSourceRegistry(
        pages=tuple(pages[key] for key in sorted(pages)),
        include_notes=include_notes,
        authoritative=True,
    )


def _atomic_json_write(
    *,
    path: Path,
    data: dict[str, Any],
    error_message: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f"{path.name}.tmp")

    try:
        with open(temporary_path, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")

        temporary_path.replace(path)
    except OSError as error:
        raise KnowledgeSourceRegistryError(error_message) from error


def _required_text(value: str, name: str) -> str:
    normalized = (value or "").strip()

    if not normalized:
        raise KnowledgeSourceRegistryError(f"{name}が指定されていません。")

    return normalized
