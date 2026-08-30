import unittest

from types import SimpleNamespace
from unittest.mock import Mock

from app.integrations import openai_embedding_client
from app.integrations.openai_embedding_client import (
    EmbeddingAPIError,
    EmbeddingConfigurationError,
    EmbeddingResponseError,
    OpenAIEmbeddingClient,
)


class OpenAIEmbeddingClientTests(unittest.TestCase):
    def test_missing_api_key_fails_when_embedding_client_is_created(self):
        with self.assertRaisesRegex(
            EmbeddingConfigurationError,
            "OPENAI_API_KEY",
        ):
            OpenAIEmbeddingClient(api_key=None)

    def test_windows_client_uses_system_trust_without_disabling_tls(self):
        ssl_context = Mock()
        ssl_context.verify_flags = (
            openai_embedding_client.ssl.VERIFY_X509_STRICT
        )
        http_client = Mock()
        sdk_client = Mock()

        with (
            unittest.mock.patch.object(
                openai_embedding_client.sys,
                "platform",
                "win32",
            ),
            unittest.mock.patch.object(
                openai_embedding_client.ssl,
                "create_default_context",
                return_value=ssl_context,
            ),
            unittest.mock.patch.object(
                openai_embedding_client.httpx,
                "Client",
                return_value=http_client,
            ) as http_client_factory,
            unittest.mock.patch.object(
                openai_embedding_client,
                "OpenAI",
                return_value=sdk_client,
            ) as openai_factory,
        ):
            client = OpenAIEmbeddingClient(api_key="secret-key")

        self.assertEqual(ssl_context.verify_flags, 0)
        http_client_factory.assert_called_once_with(
            verify=ssl_context,
            timeout=(
                openai_embedding_client.EMBEDDING_HTTP_TIMEOUT_SECONDS
            ),
        )
        openai_factory.assert_called_once_with(
            api_key="secret-key",
            http_client=http_client,
        )
        self.assertIs(client._client, sdk_client)

    def test_sends_multiple_inputs_model_dimensions_and_float_format(self):
        sdk_client = Mock()
        sdk_client.embeddings.create.return_value = SimpleNamespace(
            data=[
                SimpleNamespace(index=1, embedding=[0.4, 0.5, 0.6]),
                SimpleNamespace(index=0, embedding=[0.1, 0.2, 0.3]),
            ]
        )
        client = OpenAIEmbeddingClient(
            api_key="secret-key",
            sdk_client=sdk_client,
        )

        vectors = client.create_embeddings(
            ["first", "second"],
            model="text-embedding-3-small",
            dimensions=3,
        )

        self.assertEqual(
            vectors,
            [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
        )
        sdk_client.embeddings.create.assert_called_once_with(
            model="text-embedding-3-small",
            input=["first", "second"],
            dimensions=3,
            encoding_format="float",
        )
        self.assertNotIn("secret-key", repr(client))

    def test_rejects_empty_input_before_calling_api(self):
        sdk_client = Mock()
        client = OpenAIEmbeddingClient(
            api_key="secret-key",
            sdk_client=sdk_client,
        )

        for texts in ([], ["valid", "  "]):
            with self.subTest(texts=texts):
                with self.assertRaises(EmbeddingConfigurationError):
                    client.create_embeddings(
                        texts,
                        model="text-embedding-3-small",
                        dimensions=3,
                    )

        sdk_client.embeddings.create.assert_not_called()

    def test_rejects_wrong_response_count_index_and_dimensions(self):
        cases = (
            [],
            [SimpleNamespace(index=2, embedding=[0.1, 0.2, 0.3])],
            [SimpleNamespace(index=0, embedding=[0.1, 0.2])],
        )

        for data in cases:
            with self.subTest(data=data):
                sdk_client = Mock()
                sdk_client.embeddings.create.return_value = SimpleNamespace(
                    data=data
                )
                client = OpenAIEmbeddingClient(
                    api_key="secret-key",
                    sdk_client=sdk_client,
                )

                with self.assertRaises(EmbeddingResponseError):
                    client.create_embeddings(
                        ["input"],
                        model="text-embedding-3-small",
                        dimensions=3,
                    )

    def test_api_error_is_safe_and_does_not_expose_key_or_sdk_message(self):
        sdk_client = Mock()
        sdk_client.embeddings.create.side_effect = RuntimeError(
            "request failed with secret-key"
        )
        client = OpenAIEmbeddingClient(
            api_key="secret-key",
            sdk_client=sdk_client,
        )

        with self.assertRaises(EmbeddingAPIError) as context:
            client.create_embeddings(
                ["input"],
                model="text-embedding-3-small",
                dimensions=3,
            )

        self.assertNotIn("secret-key", str(context.exception))
        self.assertNotIn("request failed", str(context.exception))
        self.assertIsNone(context.exception.__cause__)


if __name__ == "__main__":
    unittest.main()
