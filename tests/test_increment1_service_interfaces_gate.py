"""
tests/test_increment1_service_interfaces_gate.py
===================================================
Phase v2.0, Increment 1 Gate — Service Interfaces

Hard gate proofs (must be 100% green before Increment 2):

  1. TestServiceRegistryInterfaceTypingGate
     - ServiceRegistry.controller returns VectorStoreInterface (not ChromaController)
     - ServiceRegistry.embedder returns EmbedderInterface (not OllamaEmbeddingWrapper)
     - ServiceRegistry.gateway returns ModelGatewayInterface (not OllamaModelGateway)
     - Internal singleton fields are typed against interfaces

  2. TestVectorStoreSwappabilityGate
     - A stub VectorStoreInterface can be injected into ServiceRegistry and consumed
       by retrieveKnowledge() without any changes to that capability's code.

  3. TestIncrement1RegressionGate
     - Full existing test suite passes with zero regressions (pure refactor).

Gate run command:
    python -m pytest tests/test_increment1_service_interfaces_gate.py -v

Full regression:
    python -m pytest tests/ -v
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, get_type_hints

import pytest

from abm.api.capabilities import retrieveKnowledge
from abm.api.core.config import APIConfig
from abm.api.core.interfaces import (
    EmbedderInterface,
    ModelGatewayInterface,
    VectorStoreInterface,
)
from abm.api.core.registry import ServiceRegistry
from abm.memory.chroma_controller import ALL_COLLECTIONS, QueryResult

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Stub implementations — prove swappability without ChromaDB
# ---------------------------------------------------------------------------


class StubVectorStore(VectorStoreInterface):
    """In-memory stub proving any VectorStoreInterface satisfies consumers."""

    def __init__(self) -> None:
        self.queries: list[tuple[str, list[float], int]] = []

    def get_collection(self, collection_name: str) -> Any:
        return {"name": collection_name, "backend": "stub"}

    def add_document(
        self,
        collection_name: str,
        doc_id: str,
        text: str,
        metadata: dict[str, Any],
        embedding: list[float],
    ) -> None:
        pass

    def query_collection(
        self,
        collection_name: str,
        query_embedding: list[float],
        n_results: int = 5,
    ) -> QueryResult:
        self.queries.append((collection_name, query_embedding, n_results))
        return QueryResult(
            collection_name=collection_name,
            ids=[["stub_doc"]],
            documents=[[f"stub hit from {collection_name}"]],
            metadatas=[[{"backend": "stub"}]],
            distances=[[0.01]],
        )


class StubEmbedder(EmbedderInterface):
    """Minimal embedder stub paired with StubVectorStore."""

    def health_check(self) -> bool:
        return True

    def embed(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]


def _booted_registry_with_stubs() -> tuple[ServiceRegistry, StubVectorStore]:
    registry = ServiceRegistry(APIConfig())
    stub_store = StubVectorStore()
    registry._booted = True
    registry._controller = stub_store
    registry._embedder = StubEmbedder()
    return registry, stub_store


# ===========================================================================
# Proof 1 — ServiceRegistry typed against interfaces
# ===========================================================================


class TestServiceRegistryInterfaceTypingGate:
    """Gate: registry accessors expose abstract interfaces, not concrete classes."""

    def test_controller_property_return_type_is_vector_store_interface(self):
        hints = get_type_hints(ServiceRegistry.controller.fget)
        assert hints["return"] is VectorStoreInterface

    def test_embedder_property_return_type_is_embedder_interface(self):
        hints = get_type_hints(ServiceRegistry.embedder.fget)
        assert hints["return"] is EmbedderInterface

    def test_gateway_property_return_type_is_model_gateway_interface(self):
        hints = get_type_hints(ServiceRegistry.gateway.fget)
        assert hints["return"] is ModelGatewayInterface

    def test_internal_singleton_fields_typed_as_interfaces(self):
        hints = get_type_hints(ServiceRegistry)
        assert hints["_controller"] == VectorStoreInterface | None
        assert hints["_embedder"] == EmbedderInterface | None
        assert hints["_gateway"] == ModelGatewayInterface | None

    def test_concrete_classes_implement_interfaces(self):
        from abm.memory.chroma_controller import ChromaController
        from abm.memory.embedding_wrapper import OllamaEmbeddingWrapper
        from abm.orchestrator.model_gateway import OllamaModelGateway

        assert issubclass(ChromaController, VectorStoreInterface)
        assert issubclass(OllamaEmbeddingWrapper, EmbedderInterface)
        assert issubclass(OllamaModelGateway, ModelGatewayInterface)


# ===========================================================================
# Proof 2 — VectorStoreInterface swappability
# ===========================================================================


class TestVectorStoreSwappabilityGate:
    """Gate: stub VectorStoreInterface works through unchanged consumer code."""

    def test_retrieve_knowledge_uses_injected_stub_without_code_changes(self):
        """
        retrieveKnowledge() is unchanged consumer code.  Injecting a
        StubVectorStore via ServiceRegistry.controller must route all four
        collection queries through the stub — no ChromaController required.
        """
        registry, stub_store = _booted_registry_with_stubs()

        result = retrieveKnowledge("swappability probe", registry=registry)

        assert result.degraded is False
        assert len(stub_store.queries) == len(ALL_COLLECTIONS)
        queried_collections = {q[0] for q in stub_store.queries}
        assert queried_collections == set(ALL_COLLECTIONS)
        assert any("stub hit from" in hit["text"] for hit in result.hits)
        assert all(hit["collection"] in ALL_COLLECTIONS for hit in result.hits)


# ===========================================================================
# Proof 3 — Full suite regression
# ===========================================================================


class TestIncrement1RegressionGate:
    """Gate: entire existing test suite still passes (pure refactor)."""

    def test_full_existing_suite_has_zero_regressions(self):
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "--ignore=tests/test_increment1_service_interfaces_gate.py", "-q", "--tb=no"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            "Increment 1 introduced regressions:\n"
            f"{result.stdout}\n{result.stderr}"
        )
