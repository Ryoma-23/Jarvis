import ssl
import sys

from typing import Any

import httpx
from openai import OpenAI


MAX_EMBEDDING_INPUTS = 2048
EMBEDDING_HTTP_TIMEOUT_SECONDS = 60.0


class EmbeddingError(RuntimeError):
    """Base exception for safe Embedding errors."""


class EmbeddingConfigurationError(EmbeddingError):
    """Raised when Embedding configuration is missing or invalid."""


class EmbeddingAPIError(EmbeddingError):
    """Raised when the OpenAI Embeddings API request fails."""


class EmbeddingResponseError(EmbeddingError):
    """Raised when the Embeddings API response is malformed."""


class OpenAIEmbeddingClient:
    """OpenAI client boundary used only for Embedding requests."""

    def __init__(
        self,
        *,
        api_key: str | None,
        sdk_client: Any | None = None,
    ):
        normalized_api_key = (api_key or "").strip()

        if not normalized_api_key:
            raise EmbeddingConfigurationError(
                "OPENAI_API_KEY が設定されていません。"
            )

        self._api_key = normalized_api_key
        self._client = sdk_client or _create_sdk_client(normalized_api_key)

    def __repr__(self) -> str:
        return "OpenAIEmbeddingClient()"

    def create_embeddings(
        self,
        texts: list[str],
        *,
        model: str,
        dimensions: int,
    ) -> list[list[float]]:
        normalized_model = (model or "").strip()

        if not normalized_model:
            raise EmbeddingConfigurationError(
                "OPENAI_EMBEDDING_MODEL が設定されていません。"
            )

        if not isinstance(dimensions, int) or isinstance(dimensions, bool):
            raise EmbeddingConfigurationError(
                "Embedding dimensionsは1以上の整数が必要です。"
            )

        if dimensions < 1:
            raise EmbeddingConfigurationError(
                "Embedding dimensionsは1以上の整数が必要です。"
            )

        if not isinstance(texts, list) or not texts:
            raise EmbeddingConfigurationError(
                "Embedding inputは空でないリストが必要です。"
            )

        if len(texts) > MAX_EMBEDDING_INPUTS:
            raise EmbeddingConfigurationError(
                "1回のEmbedding inputは2048件以下にしてください。"
            )

        normalized_texts = []

        for text in texts:
            if not isinstance(text, str) or not text.strip():
                raise EmbeddingConfigurationError(
                    "Embedding inputに空文字は使用できません。"
                )

            normalized_texts.append(text)

        try:
            response = self._client.embeddings.create(
                model=normalized_model,
                input=normalized_texts,
                dimensions=dimensions,
                encoding_format="float",
            )
        except Exception as error:
            status_code = getattr(error, "status_code", None)
            error_types = _safe_error_types(error)
            status_suffix = (
                f"（HTTP {status_code}）"
                if isinstance(status_code, int)
                else ""
            )
            raise EmbeddingAPIError(
                "OpenAI Embeddings APIへのリクエストに失敗しました"
                f"{status_suffix}。種別: {' -> '.join(error_types)}。"
                "再実行してください。"
            ) from None

        data = getattr(response, "data", None)

        if not isinstance(data, list) or len(data) != len(normalized_texts):
            raise EmbeddingResponseError(
                "OpenAI Embeddings APIの返却件数が一致しません。"
            )

        vectors_by_index: dict[int, list[float]] = {}

        for item in data:
            index = getattr(item, "index", None)
            embedding = getattr(item, "embedding", None)

            if (
                not isinstance(index, int)
                or isinstance(index, bool)
                or index < 0
                or index >= len(normalized_texts)
                or index in vectors_by_index
            ):
                raise EmbeddingResponseError(
                    "OpenAI Embeddings APIのindexが不正です。"
                )

            if not isinstance(embedding, list) or len(embedding) != dimensions:
                raise EmbeddingResponseError(
                    "OpenAI Embeddings APIのvector次元数が一致しません。"
                )

            vector = []

            for value in embedding:
                if (
                    not isinstance(value, (int, float))
                    or isinstance(value, bool)
                ):
                    raise EmbeddingResponseError(
                        "OpenAI Embeddings APIのvector形式が不正です。"
                    )

                vector.append(float(value))

            vectors_by_index[index] = vector

        if set(vectors_by_index) != set(range(len(normalized_texts))):
            raise EmbeddingResponseError(
                "OpenAI Embeddings APIのindexが不足しています。"
            )

        return [
            vectors_by_index[index]
            for index in range(len(normalized_texts))
        ]


def _safe_error_types(error: Exception) -> list[str]:
    names = []
    current: BaseException | None = error
    seen = set()

    while current is not None and id(current) not in seen and len(names) < 5:
        seen.add(id(current))
        names.append(type(current).__name__)
        current = current.__cause__ or current.__context__

    return names


def _create_sdk_client(api_key: str) -> OpenAI:
    if sys.platform != "win32":
        return OpenAI(api_key=api_key)

    ssl_context = ssl.create_default_context()
    strict_flag = getattr(ssl, "VERIFY_X509_STRICT", 0)

    if strict_flag:
        ssl_context.verify_flags &= ~strict_flag

    return OpenAI(
        api_key=api_key,
        http_client=httpx.Client(
            verify=ssl_context,
            timeout=EMBEDDING_HTTP_TIMEOUT_SECONDS,
        ),
    )
