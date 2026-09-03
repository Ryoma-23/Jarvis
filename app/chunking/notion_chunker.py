import hashlib

from dataclasses import dataclass
from typing import Any

from app.chunking.notion_blocks import (
    NormalizedNotionBlock,
    NotionBlockNormalizer,
    NotionBlockTreeFetcher,
)
from app.integrations.notion_client import (
    NotionClient,
    NotionConfigurationError,
    NotionResponseError,
)


DEFAULT_MAX_CHUNK_CHARACTERS = 1200
MIN_MAX_CHUNK_CHARACTERS = 100


@dataclass(frozen=True)
class NotionChunk:
    chunk_id: str
    notion_page_id: str
    block_id: str
    title: str
    chunk_index: int
    content: str
    content_hash: str
    last_edited_time: str
    source_type: str
    notion_url: str
    heading_path: tuple[str, ...]
    block_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "notion_page_id": self.notion_page_id,
            "block_id": self.block_id,
            "title": self.title,
            "chunk_index": self.chunk_index,
            "content": self.content,
            "content_hash": self.content_hash,
            "last_edited_time": self.last_edited_time,
            "source_type": self.source_type,
            "notion_url": self.notion_url,
            "heading_path": list(self.heading_path),
            "block_ids": list(self.block_ids),
        }


@dataclass(frozen=True)
class _Section:
    heading_path: tuple[tuple[int, str], ...]
    heading_block_id: str | None
    body: tuple[NormalizedNotionBlock, ...]


class NotionPageChunker:
    def __init__(
        self,
        *,
        max_chunk_characters: int = DEFAULT_MAX_CHUNK_CHARACTERS,
    ):
        if max_chunk_characters < MIN_MAX_CHUNK_CHARACTERS:
            raise NotionConfigurationError(
                "max_chunk_charactersは100以上が必要です。"
            )

        self._max_chunk_characters = max_chunk_characters

    def chunk(
        self,
        *,
        page: dict[str, Any],
        blocks: list[NormalizedNotionBlock],
        source_type: str = "notion_page",
    ) -> list[NotionChunk]:
        normalized_source_type = (source_type or "").strip()

        if not normalized_source_type:
            raise NotionConfigurationError(
                "Chunkのsource_typeが指定されていません。"
            )

        page_id = _required_page_text(page, "id")
        title = _extract_page_title(page)
        last_edited_time = _required_page_text(
            page,
            "last_edited_time",
        )
        notion_url = _required_page_text(page, "url")
        candidates = []

        for section in self._sections(blocks):
            candidates.extend(self._split_section(section))

        chunks = []
        collision_counts: dict[str, int] = {}

        for chunk_index, candidate in enumerate(candidates):
            content, anchor_block_id, heading_path, block_ids = candidate
            content_hash = _sha256(content)
            identity_source = (
                f"{_canonical_id(page_id)}\0"
                f"{_canonical_id(anchor_block_id)}\0{content_hash}"
            )
            base_chunk_id = f"notion-chunk:{_sha256(identity_source)}"
            occurrence = collision_counts.get(base_chunk_id, 0)
            collision_counts[base_chunk_id] = occurrence + 1
            chunk_id = (
                base_chunk_id
                if occurrence == 0
                else f"notion-chunk:{_sha256(f'{base_chunk_id}:{occurrence}')}"
            )
            chunks.append(
                NotionChunk(
                    chunk_id=chunk_id,
                    notion_page_id=page_id,
                    block_id=anchor_block_id,
                    title=title,
                    chunk_index=chunk_index,
                    content=content,
                    content_hash=content_hash,
                    last_edited_time=last_edited_time,
                    source_type=normalized_source_type,
                    notion_url=notion_url,
                    heading_path=heading_path,
                    block_ids=block_ids,
                )
            )

        return chunks

    def _sections(
        self,
        blocks: list[NormalizedNotionBlock],
    ) -> list[_Section]:
        sections = []
        heading_stack: list[tuple[int, str]] = []
        heading_block_id = None
        body = []

        for block in blocks:
            if block.heading_level is None:
                body.append(block)
                continue

            if body or heading_block_id is not None:
                sections.append(
                    _Section(
                        heading_path=tuple(heading_stack),
                        heading_block_id=heading_block_id,
                        body=tuple(body),
                    )
                )
                body = []

            heading_stack = [
                heading
                for heading in heading_stack
                if heading[0] < block.heading_level
            ]
            heading_stack.append((block.heading_level, block.text))
            heading_block_id = block.block_id

        if body or heading_block_id is not None:
            sections.append(
                _Section(
                    heading_path=tuple(heading_stack),
                    heading_block_id=heading_block_id,
                    body=tuple(body),
                )
            )

        return sections

    def _split_section(
        self,
        section: _Section,
    ) -> list[tuple[str, str, tuple[str, ...], tuple[str, ...]]]:
        prefix = "\n".join(
            f"{'#' * level} {text}"
            for level, text in section.heading_path
        )
        heading_path = tuple(text for _, text in section.heading_path)
        units = []
        available = max(
            1,
            self._max_chunk_characters - len(prefix) - (2 if prefix else 0),
        )

        for block in section.body:
            for part in _split_text(block.text, available):
                units.append((part, block.block_id))

        if not units and prefix:
            anchor = section.heading_block_id

            if anchor is None:
                raise NotionResponseError(
                    "見出しChunkのBlock IDを決定できませんでした。"
                )

            return [(prefix, anchor, heading_path, (anchor,))]

        if not units:
            return []

        chunks = []
        current_units = []
        current_length = len(prefix) + (2 if prefix else 0)

        for text, block_id in units:
            separator_length = 1 if current_units else 0
            candidate_length = current_length + separator_length + len(text)

            if current_units and candidate_length > self._max_chunk_characters:
                chunks.append(
                    _build_candidate(
                        prefix,
                        section.heading_block_id,
                        heading_path,
                        current_units,
                    )
                )
                current_units = []
                current_length = len(prefix) + (2 if prefix else 0)

            separator_length = 1 if current_units else 0
            current_units.append((text, block_id))
            current_length += separator_length + len(text)

        if current_units:
            chunks.append(
                _build_candidate(
                    prefix,
                    section.heading_block_id,
                    heading_path,
                    current_units,
                )
            )

        return chunks


class NotionPageChunkingService:
    def __init__(
        self,
        *,
        client: NotionClient,
        max_chunk_characters: int = DEFAULT_MAX_CHUNK_CHARACTERS,
    ):
        self._client = client
        self._fetcher = NotionBlockTreeFetcher(client=client)
        self._normalizer = NotionBlockNormalizer()
        self._chunker = NotionPageChunker(
            max_chunk_characters=max_chunk_characters
        )

    def chunk_page(self, page_id: str) -> list[NotionChunk]:
        page = self._client.retrieve_page(page_id)
        nodes = self._fetcher.fetch_page_blocks(page_id)
        blocks = self._normalizer.normalize(nodes)
        return self._chunker.chunk(page=page, blocks=blocks)


def _build_candidate(
    prefix: str,
    heading_block_id: str | None,
    heading_path: tuple[str, ...],
    units: list[tuple[str, str]],
) -> tuple[str, str, tuple[str, ...], tuple[str, ...]]:
    body = "\n".join(text for text, _ in units)
    content = f"{prefix}\n\n{body}" if prefix else body
    anchor = heading_block_id or units[0][1]
    block_ids = []

    if heading_block_id:
        block_ids.append(heading_block_id)

    for _, block_id in units:
        if block_id not in block_ids:
            block_ids.append(block_id)

    return content, anchor, heading_path, tuple(block_ids)


def _split_text(value: str, limit: int) -> list[str]:
    remaining = value.strip()
    parts = []

    while len(remaining) > limit:
        boundary = max(
            remaining.rfind("\n", 0, limit + 1),
            remaining.rfind(" ", 0, limit + 1),
        )

        if boundary <= 0:
            boundary = limit

        part = remaining[:boundary].strip()

        if part:
            parts.append(part)

        remaining = remaining[boundary:].strip()

    if remaining:
        parts.append(remaining)

    return parts


def _extract_page_title(page: dict[str, Any]) -> str:
    properties = page.get("properties")

    if not isinstance(properties, dict):
        raise NotionResponseError(
            "Notion Pageのpropertiesを取得できませんでした。"
        )

    for property_value in properties.values():
        if not isinstance(property_value, dict):
            continue

        title_items = property_value.get("title")

        if not isinstance(title_items, list):
            continue

        values = []

        for item in title_items:
            if not isinstance(item, dict):
                continue

            plain_text = item.get("plain_text")

            if isinstance(plain_text, str):
                values.append(plain_text)
                continue

            text = item.get("text")
            content = text.get("content") if isinstance(text, dict) else None

            if isinstance(content, str):
                values.append(content)

        title = " ".join("".join(values).split())

        if title:
            return title

    raise NotionResponseError(
        "Notion Pageのタイトルを取得できませんでした。"
    )


def _required_page_text(page: dict[str, Any], key: str) -> str:
    value = page.get(key)

    if not isinstance(value, str) or not value.strip():
        raise NotionResponseError(
            f"Notion Pageの{key}を取得できませんでした。"
        )

    return value.strip()


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_id(value: str) -> str:
    return value.strip().replace("-", "").lower()
