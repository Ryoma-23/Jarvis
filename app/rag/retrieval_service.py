import math

from dataclasses import dataclass
from typing import Any, Iterable

from app.integrations.openai_embedding_client import OpenAIEmbeddingClient
from app.vector.chroma_index import ChromaIndex, ChromaQueryRecord


@dataclass(frozen=True)
class RetrievedChunk:
    content: str
    score: float
    title: str
    notion_page_id: str
    notion_url: str
    source_type: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "score": self.score,
            "title": self.title,
            "notion_page_id": self.notion_page_id,
            "notion_url": self.notion_url,
            "source_type": self.source_type,
        }


class RagRetrievalError(RuntimeError):
    """Raised when standalone RAG retrieval input or data is invalid."""


@dataclass(frozen=True)
class _Candidate:
    chunk_id: str
    content: str
    score: float
    title: str
    notion_page_id: str
    notion_url: str
    source_type: str
    chunk_index: int


class RagRetrievalService:
    """Embeds one question and retrieves context without invoking an LLM."""

    def __init__(
        self,
        *,
        embedding_client: OpenAIEmbeddingClient,
        chroma_index: ChromaIndex,
        model: str,
        dimensions: int,
        top_k: int,
        min_score: float,
        max_context_tokens: int,
    ):
        normalized_model = (model or "").strip()

        if not normalized_model:
            raise RagRetrievalError(
                "RAG検索のEmbedding modelが指定されていません。"
            )

        if (
            not isinstance(dimensions, int)
            or isinstance(dimensions, bool)
            or dimensions < 1
        ):
            raise RagRetrievalError(
                "RAG検索のdimensionsは1以上の整数が必要です。"
            )

        if (
            not isinstance(top_k, int)
            or isinstance(top_k, bool)
            or top_k < 1
        ):
            raise RagRetrievalError(
                "RAG検索のTop Kは1以上の整数が必要です。"
            )

        if (
            not isinstance(min_score, (int, float))
            or isinstance(min_score, bool)
            or not math.isfinite(float(min_score))
            or not 0.0 <= float(min_score) <= 1.0
        ):
            raise RagRetrievalError(
                "RAG検索の類似度閾値は0以上1以下が必要です。"
            )

        if (
            not isinstance(max_context_tokens, int)
            or isinstance(max_context_tokens, bool)
            or max_context_tokens < 1
        ):
            raise RagRetrievalError(
                "RAG検索のContext token上限は1以上の整数が必要です。"
            )

        if (
            chroma_index.model != normalized_model
            or chroma_index.dimensions != dimensions
        ):
            raise RagRetrievalError(
                "RAG検索とChroma CollectionのEmbedding設定が一致しません。"
            )

        self._embedding_client = embedding_client
        self._chroma_index = chroma_index
        self._model = normalized_model
        self._dimensions = dimensions
        self._top_k = top_k
        self._min_score = float(min_score)
        self._max_context_tokens = max_context_tokens

    def retrieve(self, question: str) -> list[RetrievedChunk]:
        normalized_question = (question or "").strip()

        if not normalized_question:
            raise RagRetrievalError("RAG検索の質問が空です。")

        embeddings = self._embedding_client.create_embeddings(
            [normalized_question],
            model=self._model,
            dimensions=self._dimensions,
        )

        if len(embeddings) != 1:
            raise RagRetrievalError(
                "RAG検索の質問Embeddingを1件取得できませんでした。"
            )

        records = self._chroma_index.query(
            embeddings[0],
            n_results=self._top_k,
        )
        candidates = [self._candidate(record) for record in records]
        candidates = [
            candidate
            for candidate in candidates
            if candidate.score >= self._min_score
        ]
        unique_candidates = _remove_exact_duplicates(candidates)
        retrieved = _merge_nearby_chunks(unique_candidates)
        retrieved.sort(
            key=lambda item: (
                -item.score,
                item.notion_page_id,
                item.title,
            )
        )
        return _apply_context_budget(
            retrieved,
            max_tokens=self._max_context_tokens,
        )

    def _candidate(self, record: ChromaQueryRecord) -> _Candidate:
        metadata = record.metadata
        chunk_index = metadata.get("chunk_index")

        if (
            not isinstance(chunk_index, int)
            or isinstance(chunk_index, bool)
            or chunk_index < 0
        ):
            raise RagRetrievalError(
                "Chroma検索結果のchunk_indexが不正です。"
            )

        return _Candidate(
            chunk_id=record.chunk_id,
            content=record.document.strip(),
            score=distance_to_score(record.distance),
            title=_required_metadata_text(metadata, "title"),
            notion_page_id=_required_metadata_text(
                metadata,
                "notion_page_id",
            ),
            notion_url=_required_metadata_text(metadata, "notion_url"),
            source_type=_required_metadata_text(metadata, "source_type"),
            chunk_index=chunk_index,
        )


def distance_to_score(distance: float) -> float:
    if (
        not isinstance(distance, (int, float))
        or isinstance(distance, bool)
        or not math.isfinite(float(distance))
        or float(distance) < 0
    ):
        raise RagRetrievalError("Chroma検索結果のdistanceが不正です。")

    return 1.0 / (1.0 + float(distance))


def estimate_token_count(value: str) -> int:
    """Return a conservative token upper bound for byte-level tokenizers."""
    return len((value or "").encode("utf-8"))


def estimate_retrieved_tokens(chunks: Iterable[RetrievedChunk]) -> int:
    return sum(
        estimate_token_count(f"{chunk.title}\n{chunk.content}")
        for chunk in chunks
    )


def _required_metadata_text(metadata: dict[str, Any], key: str) -> str:
    value = metadata.get(key)

    if not isinstance(value, str) or not value.strip():
        raise RagRetrievalError(
            f"Chroma検索結果の{key}が不正です。"
        )

    return value.strip()


def _remove_exact_duplicates(
    candidates: list[_Candidate],
) -> list[_Candidate]:
    unique = []
    seen = set()

    for candidate in sorted(
        candidates,
        key=lambda item: (-item.score, item.chunk_id),
    ):
        content_key = " ".join(candidate.content.split()).casefold()
        key = (candidate.notion_page_id, content_key)

        if key in seen:
            continue

        seen.add(key)
        unique.append(candidate)

    return unique


def _merge_nearby_chunks(
    candidates: list[_Candidate],
) -> list[RetrievedChunk]:
    candidates_by_page: dict[str, list[_Candidate]] = {}

    for candidate in candidates:
        candidates_by_page.setdefault(
            candidate.notion_page_id,
            [],
        ).append(candidate)

    groups = []

    for page_candidates in candidates_by_page.values():
        current = []
        previous_index = None

        for candidate in sorted(
            page_candidates,
            key=lambda item: (item.chunk_index, -item.score, item.chunk_id),
        ):
            if (
                current
                and previous_index is not None
                and candidate.chunk_index > previous_index + 1
            ):
                groups.append(current)
                current = []

            current.append(candidate)
            previous_index = candidate.chunk_index

        if current:
            groups.append(current)

    return [_merge_candidate_group(group) for group in groups]


def _merge_candidate_group(group: list[_Candidate]) -> RetrievedChunk:
    representative = max(group, key=lambda item: item.score)
    content = ""

    for candidate in group:
        content = _merge_neighbor_content(content, candidate.content)

    return RetrievedChunk(
        content=content,
        score=representative.score,
        title=representative.title,
        notion_page_id=representative.notion_page_id,
        notion_url=representative.notion_url,
        source_type=representative.source_type,
    )


def _merge_neighbor_content(current: str, following: str) -> str:
    first = current.strip()
    second = following.strip()

    if not first:
        return second

    if not second or second == first:
        return first

    first_lines = first.splitlines()
    second_lines = second.splitlines()
    repeated_prefix = 0

    while repeated_prefix < min(len(first_lines), len(second_lines)):
        first_line = first_lines[repeated_prefix].strip()
        second_line = second_lines[repeated_prefix].strip()

        if first_line != second_line:
            break

        if first_line and not first_line.startswith("#"):
            break

        repeated_prefix += 1

    remaining_lines = second_lines[repeated_prefix:]

    if not remaining_lines:
        return first

    maximum_overlap = min(len(first_lines), len(remaining_lines))

    for overlap in range(maximum_overlap, 0, -1):
        if first_lines[-overlap:] == remaining_lines[:overlap]:
            remaining_lines = remaining_lines[overlap:]
            break

    remainder = "\n".join(remaining_lines).strip()
    return f"{first}\n\n{remainder}" if remainder else first


def _apply_context_budget(
    chunks: list[RetrievedChunk],
    *,
    max_tokens: int,
) -> list[RetrievedChunk]:
    selected = []
    remaining = max_tokens

    for chunk in chunks:
        title_cost = estimate_token_count(f"{chunk.title}\n")
        content_budget = remaining - title_cost

        if content_budget < 1:
            continue

        content = _truncate_to_token_budget(
            chunk.content,
            content_budget,
        )

        if not content:
            continue

        selected_chunk = RetrievedChunk(
            content=content,
            score=chunk.score,
            title=chunk.title,
            notion_page_id=chunk.notion_page_id,
            notion_url=chunk.notion_url,
            source_type=chunk.source_type,
        )
        selected.append(selected_chunk)
        remaining -= estimate_token_count(
            f"{selected_chunk.title}\n{selected_chunk.content}"
        )

        if remaining < 1:
            break

    return selected


def _truncate_to_token_budget(value: str, max_tokens: int) -> str:
    normalized = value.strip()

    if estimate_token_count(normalized) <= max_tokens:
        return normalized

    ellipsis = "…"
    ellipsis_cost = estimate_token_count(ellipsis)

    if max_tokens <= ellipsis_cost:
        return ""

    low = 0
    high = len(normalized)

    while low < high:
        middle = (low + high + 1) // 2
        candidate = normalized[:middle].rstrip()

        if estimate_token_count(candidate) + ellipsis_cost <= max_tokens:
            low = middle
        else:
            high = middle - 1

    prefix = normalized[:low].rstrip()
    return f"{prefix}{ellipsis}" if prefix else ""
