"""
abm/api/core/interfaces.py
==========================
Abstract service interfaces for the ABM 2.0 architecture.

These interfaces define the contracts for core system dependencies
(Vector Store, Embedder, Model Gateway). By relying on these interfaces
instead of concrete implementations, the ServiceRegistry enables
swappable components (e.g. replacing ChromaDB with another vector
store) without breaking downstream clients.
"""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Use TYPE_CHECKING to avoid circular imports, as the concrete
    # implementations will import these interfaces to inherit from them.
    from abm.memory.chroma_controller import QueryResult
    from abm.orchestrator.model_gateway import GenerationResponse


class VectorStoreInterface(abc.ABC):
    """
    Abstract interface for vector database operations.
    """

    @abc.abstractmethod
    def get_collection(self, collection_name: str) -> Any:
        """
        Return the handle for the given collection name.
        """
        pass

    @abc.abstractmethod
    def add_document(
        self,
        collection_name: str,
        doc_id: str,
        text: str,
        metadata: dict[str, Any],
        embedding: list[float],
    ) -> None:
        """
        Add a single document with a pre-computed embedding to the collection.
        """
        pass

    @abc.abstractmethod
    def query_collection(
        self,
        collection_name: str,
        query_embedding: list[float],
        n_results: int = 5,
    ) -> QueryResult:
        """
        Perform a nearest-neighbour vector query against the collection.
        """
        pass


class EmbedderInterface(abc.ABC):
    """
    Abstract interface for text embedding generation.
    """

    @abc.abstractmethod
    def health_check(self) -> bool:
        """
        Verify that the embedding provider is reachable.
        """
        pass

    @abc.abstractmethod
    def embed(self, text: str) -> list[float]:
        """
        Generate a single embedding vector for the given text.
        """
        pass

    @abc.abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embedding vectors for a list of texts.
        """
        pass


class ModelGatewayInterface(abc.ABC):
    """
    Abstract interface for the text-generation model gateway.
    """

    @abc.abstractmethod
    def generate(self, prompt: str) -> GenerationResponse:
        """
        Send a prompt to the model and return the generated text.
        """
        pass

    @abc.abstractmethod
    def is_available(self) -> bool:
        """
        Check whether the model gateway is reachable and ready.
        """
        pass
