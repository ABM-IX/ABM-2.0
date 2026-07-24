"""
abm/memory/embedding_wrapper.py
================================
Ollama Embedding Connector — nomic-embed-text via local loopback
Spec Reference: ABM_SPEC.md sections 4 and 10

Wraps the Ollama HTTP API to produce text embeddings using nomic-embed-text.
All requests route exclusively through 127.0.0.1:11434 as mandated by spec
section 4. No cloud embedding providers are permitted.

Model: nomic-embed-text
Endpoint: http://127.0.0.1:11434/api/embeddings
"""

from __future__ import annotations

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (spec section 4 mandate — local loopback only)
# ---------------------------------------------------------------------------

OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
OLLAMA_EMBED_ENDPOINT: str = f"{OLLAMA_BASE_URL}/api/embeddings"
OLLAMA_TAGS_ENDPOINT: str = f"{OLLAMA_BASE_URL}/api/tags"

#: Standalone embedding model as specified in ABM_SPEC.md section 4.
#: Used exclusively for vectorization generation processing to guarantee
#: mathematical vector consistency across all memory indexing operations.
EMBEDDING_MODEL: str = "nomic-embed-text"

# Default HTTP timeouts (seconds)
CONNECT_TIMEOUT: float = 5.0
READ_TIMEOUT: float = 30.0


# ---------------------------------------------------------------------------
# OllamaEmbeddingWrapper
# ---------------------------------------------------------------------------


from abm.api.core.interfaces import EmbedderInterface


class OllamaEmbeddingWrapper(EmbedderInterface):
    """
    Connects to a local Ollama instance and produces text embeddings using
    ``nomic-embed-text``.

    All embedding requests are sent to ``127.0.0.1:11434`` via the Ollama
    HTTP API. This class never routes to external cloud providers.

    Parameters
    ----------
    base_url : str
        The Ollama server base URL. Defaults to ``"http://127.0.0.1:11434"``.
        Override only for testing; production always uses the loopback address.
    model : str
        The Ollama model name for embeddings. Defaults to ``"nomic-embed-text"``.
    connect_timeout : float
        TCP connection timeout in seconds. Defaults to ``5.0``.
    read_timeout : float
        Response read timeout in seconds. Defaults to ``30.0``.
    """

    def __init__(
        self,
        base_url: str = OLLAMA_BASE_URL,
        model: str = EMBEDDING_MODEL,
        connect_timeout: float = CONNECT_TIMEOUT,
        read_timeout: float = READ_TIMEOUT,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._embed_endpoint = f"{self._base_url}/api/embeddings"
        self._tags_endpoint = f"{self._base_url}/api/tags"
        self._model = model
        self._timeout = (connect_timeout, read_timeout)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def model(self) -> str:
        """The Ollama model name used for embedding generation."""
        return self._model

    @property
    def base_url(self) -> str:
        """The Ollama server base URL this wrapper is configured against."""
        return self._base_url

    @property
    def embed_endpoint(self) -> str:
        """The full Ollama embeddings API endpoint URL."""
        return self._embed_endpoint

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def health_check(self) -> bool:
        """
        Verify that the Ollama server is reachable and responding.

        Makes a lightweight GET request to ``/api/tags`` and checks for an
        HTTP 200 response. Does not validate that ``nomic-embed-text``
        specifically is loaded.

        Returns
        -------
        bool
            ``True`` if Ollama is reachable, ``False`` otherwise.
        """
        try:
            resp = requests.get(self._tags_endpoint, timeout=self._timeout)
            reachable = resp.status_code == 200
            logger.info(
                "Ollama health check at '%s': %s.",
                self._tags_endpoint,
                "OK" if reachable else f"HTTP {resp.status_code}",
            )
            return reachable
        except requests.ConnectionError:
            logger.warning(
                "Ollama health check failed — server not reachable at '%s'.",
                self._base_url,
            )
            return False
        except requests.Timeout:
            logger.warning(
                "Ollama health check timed out at '%s'.", self._base_url
            )
            return False

    def embed(self, text: str) -> list[float]:
        """
        Generate a single embedding vector for the given text.

        Sends a POST request to Ollama's ``/api/embeddings`` endpoint using
        the ``nomic-embed-text`` model.

        Parameters
        ----------
        text : str
            The input text to embed. Must be non-empty.

        Returns
        -------
        list[float]
            The embedding vector as a list of floats.

        Raises
        ------
        ValueError
            If ``text`` is empty.
        ConnectionError
            If Ollama is not reachable.
        RuntimeError
            If the Ollama API returns an error response or unexpected payload.
        """
        if not text or not text.strip():
            raise ValueError("OllamaEmbeddingWrapper.embed: text must be non-empty.")

        payload = {"model": self._model, "prompt": text}

        try:
            resp = requests.post(
                self._embed_endpoint,
                json=payload,
                timeout=self._timeout,
            )
        except requests.ConnectionError as exc:
            raise ConnectionError(
                f"OllamaEmbeddingWrapper: cannot reach Ollama at '{self._base_url}'. "
                "Ensure Ollama is running locally on port 11434."
            ) from exc
        except requests.Timeout as exc:
            raise RuntimeError(
                f"OllamaEmbeddingWrapper: request to '{self._embed_endpoint}' timed out."
            ) from exc

        if resp.status_code != 200:
            raise RuntimeError(
                f"OllamaEmbeddingWrapper: Ollama returned HTTP {resp.status_code}. "
                f"Body: {resp.text[:300]}"
            )

        body = resp.json()
        embedding: Optional[list[float]] = body.get("embedding")

        if not isinstance(embedding, list) or len(embedding) == 0:
            raise RuntimeError(
                f"OllamaEmbeddingWrapper: unexpected response shape from Ollama. "
                f"Expected {{'embedding': [float, ...]}}. Got: {body}"
            )

        logger.debug(
            "Embedded %d chars via '%s' → %d-dim vector.",
            len(text),
            self._model,
            len(embedding),
        )
        return embedding

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embedding vectors for a list of texts.

        Calls ``embed()`` sequentially for each text. The Ollama HTTP API
        does not natively batch embeddings in a single request, so this
        method provides a clean batch interface while handling each text
        individually.

        Parameters
        ----------
        texts : list[str]
            A list of non-empty text strings to embed.

        Returns
        -------
        list[list[float]]
            A list of embedding vectors, one per input text, in the same
            order as ``texts``.

        Raises
        ------
        ValueError
            If ``texts`` is empty, or any individual text is empty.
        ConnectionError
            If Ollama is not reachable.
        RuntimeError
            If any individual embedding call fails.
        """
        if not texts:
            raise ValueError(
                "OllamaEmbeddingWrapper.embed_batch: texts list must not be empty."
            )
        return [self.embed(text) for text in texts]
