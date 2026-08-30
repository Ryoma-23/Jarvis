from dataclasses import dataclass
from typing import Any

from app.integrations.notion_client import (
    NotionClient,
    NotionConfigurationError,
    NotionResponseError,
)


BLOCK_CHILDREN_PAGE_SIZE = 100
MAX_BLOCK_DEPTH = 64


@dataclass(frozen=True)
class NotionBlockNode:
    block: dict[str, Any]
    parent_id: str
    depth: int
    children: tuple["NotionBlockNode", ...]

    @property
    def block_id(self) -> str:
        value = self.block.get("id")

        if not isinstance(value, str):
            raise NotionResponseError(
                "Notion BlockにBlock IDがありません。"
            )

        return value


@dataclass(frozen=True)
class NormalizedNotionBlock:
    block_id: str
    block_type: str
    text: str
    depth: int
    parent_id: str
    heading_level: int | None
    last_edited_time: str | None


class NotionBlockTreeFetcher:
    def __init__(
        self,
        *,
        client: NotionClient,
        max_depth: int = MAX_BLOCK_DEPTH,
    ):
        if max_depth < 1:
            raise NotionConfigurationError(
                "Block再帰取得のmax_depthは1以上が必要です。"
            )

        self._client = client
        self._max_depth = max_depth

    def fetch_page_blocks(
        self,
        page_id: str,
    ) -> tuple[NotionBlockNode, ...]:
        normalized_page_id = (page_id or "").strip()

        if not normalized_page_id:
            raise NotionConfigurationError(
                "Notion Page IDが指定されていません。"
            )

        return self._fetch_children(
            normalized_page_id,
            depth=0,
            ancestors=frozenset(),
        )

    def _fetch_children(
        self,
        parent_id: str,
        *,
        depth: int,
        ancestors: frozenset[str],
    ) -> tuple[NotionBlockNode, ...]:
        if depth >= self._max_depth:
            raise NotionResponseError(
                "Notion Blockの再帰深度が上限を超えました。"
            )

        blocks = self._retrieve_all_children(parent_id)
        nodes = []

        for block in blocks:
            block_id = _required_block_text(block, "id")
            block_type = _required_block_text(block, "type")
            has_children = block.get("has_children")

            if not isinstance(has_children, bool):
                raise NotionResponseError(
                    f"Notion Block {block_id} のhas_childrenが不正です。"
                )

            if block_type == "unsupported" and not has_children:
                children = ()
            elif has_children:
                canonical_id = _canonical_id(block_id)

                if canonical_id in ancestors:
                    raise NotionResponseError(
                        "Notion Blockの循環参照を検出しました。"
                    )

                children = self._fetch_children(
                    block_id,
                    depth=depth + 1,
                    ancestors=ancestors | {canonical_id},
                )
            else:
                children = ()

            nodes.append(
                NotionBlockNode(
                    block=block,
                    parent_id=parent_id,
                    depth=depth,
                    children=children,
                )
            )

        return tuple(nodes)

    def _retrieve_all_children(
        self,
        parent_id: str,
    ) -> list[dict[str, Any]]:
        blocks = []
        start_cursor = None
        seen_cursors = set()
        seen_block_ids = set()

        while True:
            response = self._client.retrieve_block_children(
                parent_id,
                start_cursor=start_cursor,
                page_size=BLOCK_CHILDREN_PAGE_SIZE,
            )
            results = response.get("results")
            has_more = response.get("has_more")

            if not isinstance(results, list):
                raise NotionResponseError(
                    "Block Childrenのresultsを取得できませんでした。"
                )

            if not isinstance(has_more, bool):
                raise NotionResponseError(
                    "Block Childrenのhas_moreを取得できませんでした。"
                )

            for block in results:
                if not isinstance(block, dict):
                    raise NotionResponseError(
                        "Block Childrenに不正なBlockが含まれています。"
                    )

                block_id = _required_block_text(block, "id")
                canonical_id = _canonical_id(block_id)

                if canonical_id in seen_block_ids:
                    raise NotionResponseError(
                        f"Block Childrenに重複Blockがあります: {block_id}"
                    )

                seen_block_ids.add(canonical_id)
                blocks.append(block)

            if not has_more:
                return blocks

            next_cursor = response.get("next_cursor")

            if (
                not isinstance(next_cursor, str)
                or not next_cursor.strip()
                or next_cursor in seen_cursors
            ):
                raise NotionResponseError(
                    "Block Childrenのページネーション情報が不正です。"
                )

            seen_cursors.add(next_cursor)
            start_cursor = next_cursor


class NotionBlockNormalizer:
    def normalize(
        self,
        nodes: tuple[NotionBlockNode, ...],
    ) -> list[NormalizedNotionBlock]:
        normalized = []

        for node in nodes:
            block = self._normalize_node(node)

            if block is not None:
                normalized.append(block)

            normalized.extend(self.normalize(node.children))

        return normalized

    def _normalize_node(
        self,
        node: NotionBlockNode,
    ) -> NormalizedNotionBlock | None:
        block = node.block
        block_id = _required_block_text(block, "id")
        block_type = _required_block_text(block, "type")
        payload = block.get(block_type)
        heading_level = _heading_level(block_type)
        text = self._text_for_block(block_type, payload, node.depth)

        if not text or not text.strip():
            return None

        last_edited_time = block.get("last_edited_time")
        return NormalizedNotionBlock(
            block_id=block_id,
            block_type=block_type,
            text=text.strip(),
            depth=node.depth,
            parent_id=node.parent_id,
            heading_level=heading_level,
            last_edited_time=(
                last_edited_time.strip()
                if isinstance(last_edited_time, str)
                and last_edited_time.strip()
                else None
            ),
        )

    def _text_for_block(
        self,
        block_type: str,
        payload: Any,
        depth: int,
    ) -> str | None:
        if block_type in {
            "paragraph",
            "heading_1",
            "heading_2",
            "heading_3",
            "heading_4",
            "quote",
            "toggle",
            "template",
            "callout",
        }:
            text = _normalized_rich_text(payload)

            if block_type == "quote" and text:
                return f"> {text}"

            return text

        if block_type in {"bulleted_list_item", "numbered_list_item"}:
            text = _normalized_rich_text(payload)

            if not text:
                return None

            marker = "-" if block_type == "bulleted_list_item" else "1."
            return f"{'  ' * depth}{marker} {text}"

        if block_type == "to_do":
            text = _normalized_rich_text(payload)

            if not text:
                return None

            checked = (
                payload.get("checked")
                if isinstance(payload, dict)
                else False
            )
            marker = "x" if checked is True else " "
            return f"{'  ' * depth}- [{marker}] {text}"

        if block_type == "code":
            code = _raw_rich_text(payload)

            if not code.strip():
                return None

            language = (
                payload.get("language")
                if isinstance(payload, dict)
                else None
            )
            label = (
                f"Code ({language})"
                if isinstance(language, str)
                and language not in {"plain text", "plain_text"}
                else "Code"
            )
            return f"{label}:\n{code.strip()}"

        if block_type == "equation" and isinstance(payload, dict):
            expression = payload.get("expression")
            return expression.strip() if isinstance(expression, str) else None

        if block_type in {"child_page", "child_database"}:
            title = payload.get("title") if isinstance(payload, dict) else None
            return _normalize_inline_text(title)

        if block_type == "table_row" and isinstance(payload, dict):
            cells = payload.get("cells")

            if not isinstance(cells, list):
                return None

            values = [
                _normalize_inline_text(_plain_text(cell))
                for cell in cells
                if isinstance(cell, list)
            ]
            values = [value for value in values if value]
            return " | ".join(values) if values else None

        if block_type in {"bookmark", "embed", "link_preview"}:
            if not isinstance(payload, dict):
                return None

            caption = _normalized_rich_text(payload, key="caption")
            url = payload.get("url")
            values = [
                value
                for value in (caption, url if isinstance(url, str) else None)
                if value and value.strip()
            ]
            return " ".join(values) if values else None

        if block_type in {"image", "video", "pdf", "file", "audio"}:
            return _normalized_rich_text(payload, key="caption")

        return None


def _normalized_rich_text(
    payload: Any,
    *,
    key: str = "rich_text",
) -> str | None:
    if not isinstance(payload, dict):
        return None

    rich_text = payload.get(key)

    if not isinstance(rich_text, list):
        return None

    return _normalize_inline_text(_plain_text(rich_text))


def _raw_rich_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""

    rich_text = payload.get("rich_text")
    return _plain_text(rich_text) if isinstance(rich_text, list) else ""


def _plain_text(rich_text: list[Any]) -> str:
    values = []

    for item in rich_text:
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

    return "".join(values)


def _normalize_inline_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    normalized = " ".join(value.split())
    return normalized or None


def _heading_level(block_type: str) -> int | None:
    if not block_type.startswith("heading_"):
        return None

    suffix = block_type.removeprefix("heading_")
    return int(suffix) if suffix in {"1", "2", "3", "4"} else None


def _required_block_text(block: dict[str, Any], key: str) -> str:
    value = block.get(key)

    if not isinstance(value, str) or not value.strip():
        raise NotionResponseError(
            f"Notion Blockの{key}を取得できませんでした。"
        )

    return value.strip()


def _canonical_id(value: str) -> str:
    return value.strip().replace("-", "").lower()
