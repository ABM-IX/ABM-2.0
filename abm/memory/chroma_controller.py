"""
abm/memory/chroma_controller.py
================================
ChromaDB Controller — Quad-Stream High-Density Memory Architecture
Spec Reference: ABM_SPEC.md section 3

Manages the four isolated ChromaDB collections defined in the spec.
Data crossover or inter-collection bleed is blocked by process separation
rules enforced here at the API boundary.

Collections (spec section 3):
  - abm_cognitive_identity  : Stream D — identity, goals, corporate philosophy
  - abm_code_topologies     : Stream A — engineering DNA, code patterns
  - abm_technical_mastery   : Stream B — validated docs, API refs, package schemas
  - abm_ambient_telemetry   : Stream C — interaction history, terminal I/O, events

All metadata schemas are verbatim from spec section 3. Field names are NOT
renamed or restructured.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical collection names (spec section 3 — do not rename)
# ---------------------------------------------------------------------------

COLLECTION_COGNITIVE_IDENTITY = "abm_cognitive_identity"
COLLECTION_CODE_TOPOLOGIES = "abm_code_topologies"
COLLECTION_TECHNICAL_MASTERY = "abm_technical_mastery"
COLLECTION_AMBIENT_TELEMETRY = "abm_ambient_telemetry"

ALL_COLLECTIONS: tuple[str, ...] = (
    COLLECTION_COGNITIVE_IDENTITY,
    COLLECTION_CODE_TOPOLOGIES,
    COLLECTION_TECHNICAL_MASTERY,
    COLLECTION_AMBIENT_TELEMETRY,
)

# ---------------------------------------------------------------------------
# Canonical metadata schemas (spec section 3 — verbatim, no field renaming)
# ---------------------------------------------------------------------------

#: Stream D — identity foundations, personal/professional goals, FirstMinds
#: corporate philosophies.
SCHEMA_COGNITIVE_IDENTITY: dict[str, str] = {
    "owner": "ABM",
    "target_entity": "FirstMinds",
    "volatility": "immutable",
}

#: Stream A — personal engineering DNA, formatting signatures, pattern designs.
#: Supports dart|kotlin|python languages, flutter framework, bloc state pattern.
SCHEMA_CODE_TOPOLOGIES: dict[str, str] = {
    "language": "dart|kotlin|python",
    "framework": "flutter",
    "state_pattern": "bloc",
    "naming_convention": "camelCase",
}

#: Stream B — validated technical assets, documentation, API references,
#: external package schemas.
SCHEMA_TECHNICAL_MASTERY: dict[str, str] = {
    "source": "duckduckgo_sandbox|docs_fetch",
    "date_acquired": "2026-07-18",
    "confidence_score": "0.92",
}

#: Stream C — chronological interaction history, terminal I/O, clipboard
#: deltas, voice notes. device_source uses dynamic variable per spec
#: hardware-agnostic blueprint update (spec section 10, bottom).
SCHEMA_AMBIENT_TELEMETRY: dict[str, Any] = {
    "epoch_timestamp": 1784370192,
    "active_repository": "smart_transit|houseconnect",
    "device_source": "dynamic_mobile_node",
}

# Map each collection to its canonical metadata schema
COLLECTION_SCHEMAS: dict[str, dict[str, Any]] = {
    COLLECTION_COGNITIVE_IDENTITY: SCHEMA_COGNITIVE_IDENTITY,
    COLLECTION_CODE_TOPOLOGIES: SCHEMA_CODE_TOPOLOGIES,
    COLLECTION_TECHNICAL_MASTERY: SCHEMA_TECHNICAL_MASTERY,
    COLLECTION_AMBIENT_TELEMETRY: SCHEMA_AMBIENT_TELEMETRY,
}

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class QueryResult:
    """Typed container for a ChromaDB query response from a single collection."""

    collection_name: str
    ids: list[list[str]] = field(default_factory=list)
    documents: list[list[str]] = field(default_factory=list)
    metadatas: list[list[dict[str, Any]]] = field(default_factory=list)
    distances: list[list[float]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# ChromaController
# ---------------------------------------------------------------------------


class ChromaController:
    """
    Manages all ChromaDB collection lifecycle operations for ABM 2.0.

    The controller creates (or retrieves) the four spec-defined collections
    on initialization and provides a strict, named-collection API to prevent
    accidental cross-collection writes or queries.

    Parameters
    ----------
    persist_directory : str
        Filesystem path where ChromaDB persists its data.
        Defaults to ``"./memory/chroma_store"`` relative to the working dir.
    in_memory : bool
        If ``True``, uses an ephemeral in-memory ChromaDB client (suitable
        for testing). Overrides ``persist_directory``. Defaults to ``False``.
    """

    def __init__(
        self,
        persist_directory: str = "./memory/chroma_store",
        *,
        in_memory: bool = False,
    ) -> None:
        self._persist_directory = persist_directory
        self._in_memory = in_memory
        self._client: chromadb.ClientAPI = self._build_client()
        self._collections: dict[str, chromadb.Collection] = {}
        self.initialize_collections()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_client(self) -> chromadb.ClientAPI:
        """Construct the appropriate ChromaDB client based on config."""
        if self._in_memory:
            logger.info("ChromaController: starting ephemeral in-memory client.")
            return chromadb.EphemeralClient()
        logger.info(
            "ChromaController: starting persistent client at '%s'.",
            self._persist_directory,
        )
        return chromadb.PersistentClient(path=self._persist_directory)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def initialize_collections(self) -> None:
        """
        Create or retrieve all four spec-defined ChromaDB collections.

        Idempotent — safe to call multiple times. Uses
        ``get_or_create_collection`` so existing data is never wiped on
        restart.

        Raises
        ------
        RuntimeError
            If ChromaDB fails to create or retrieve any collection.
        """
        for name in ALL_COLLECTIONS:
            try:
                collection = self._client.get_or_create_collection(
                    name=name,
                    metadata={"hnsw:space": "cosine"},
                )
                self._collections[name] = collection
                logger.info("Collection registered: '%s'.", name)
            except Exception as exc:
                raise RuntimeError(
                    f"ChromaController: failed to initialize collection '{name}'."
                ) from exc

        logger.info(
            "All %d collections initialized: %s",
            len(ALL_COLLECTIONS),
            list(ALL_COLLECTIONS),
        )

    def get_collection(self, collection_name: str) -> chromadb.Collection:
        """
        Return the ChromaDB Collection handle for the given name.

        Parameters
        ----------
        collection_name : str
            One of the four canonical collection name constants.

        Returns
        -------
        chromadb.Collection

        Raises
        ------
        ValueError
            If ``collection_name`` is not one of the four spec-defined names.
        """
        if collection_name not in self._collections:
            raise ValueError(
                f"Unknown collection '{collection_name}'. "
                f"Must be one of: {list(ALL_COLLECTIONS)}."
            )
        return self._collections[collection_name]

    def add_document(
        self,
        collection_name: str,
        doc_id: str,
        text: str,
        metadata: dict[str, Any],
        embedding: list[float],
    ) -> None:
        """
        Add a single document with a pre-computed embedding to the named
        collection.

        The collection is resolved by name before the write, ensuring the
        document can never be routed to the wrong collection.

        Parameters
        ----------
        collection_name : str
            Target collection. Must be one of the four canonical names.
        doc_id : str
            Unique document identifier (used as ChromaDB's ``id``).
        text : str
            Raw document text stored alongside the embedding.
        metadata : dict[str, Any]
            Document metadata. Should conform to the collection's canonical
            schema (see ``COLLECTION_SCHEMAS``).
        embedding : list[float]
            Pre-computed embedding vector from ``OllamaEmbeddingWrapper``.

        Raises
        ------
        ValueError
            If ``collection_name`` is not a valid spec-defined collection.
        RuntimeError
            If the ChromaDB upsert fails.
        """
        collection = self.get_collection(collection_name)
        try:
            collection.upsert(
                ids=[doc_id],
                documents=[text],
                metadatas=[metadata],
                embeddings=[embedding],
            )
            logger.debug(
                "Document '%s' written to collection '%s'.", doc_id, collection_name
            )
        except Exception as exc:
            raise RuntimeError(
                f"ChromaController: failed to add document '{doc_id}' "
                f"to collection '{collection_name}'."
            ) from exc

    def query_collection(
        self,
        collection_name: str,
        query_embedding: list[float],
        n_results: int = 5,
    ) -> QueryResult:
        """
        Perform a nearest-neighbour vector query against the named collection.

        Parameters
        ----------
        collection_name : str
            Target collection. Must be one of the four canonical names.
        query_embedding : list[float]
            The query vector, typically produced by ``OllamaEmbeddingWrapper``.
        n_results : int
            Maximum number of results to return. Defaults to 5.

        Returns
        -------
        QueryResult
            A typed container with ids, documents, metadatas, and distances.
            All inner lists will be empty if the collection has no data.

        Raises
        ------
        ValueError
            If ``collection_name`` is not a valid spec-defined collection.
        """
        collection = self.get_collection(collection_name)

        # Guard: ChromaDB raises if n_results > collection count
        count = collection.count()
        effective_n = min(n_results, count) if count > 0 else 0

        if effective_n == 0:
            return QueryResult(collection_name=collection_name)

        raw = collection.query(
            query_embeddings=[query_embedding],
            n_results=effective_n,
            include=["documents", "metadatas", "distances"],
        )
        return QueryResult(
            collection_name=collection_name,
            ids=raw.get("ids", []),
            documents=raw.get("documents", []),
            metadatas=raw.get("metadatas", []),
            distances=raw.get("distances", []),
        )

    def clear_collection(self, collection_name: str) -> None:
        """
        Delete all documents from the named collection.

        Intended for test teardown only. The collection itself is preserved
        (not deleted), so the schema registration remains intact.

        Parameters
        ----------
        collection_name : str
            Target collection. Must be one of the four canonical names.

        Raises
        ------
        ValueError
            If ``collection_name`` is not a valid spec-defined collection.
        """
        collection = self.get_collection(collection_name)
        existing_ids = collection.get(include=[])["ids"]
        if existing_ids:
            collection.delete(ids=existing_ids)
            logger.debug(
                "Cleared %d documents from collection '%s'.",
                len(existing_ids),
                collection_name,
            )

    def collection_count(self, collection_name: str) -> int:
        """
        Return the number of documents currently stored in the named collection.

        Parameters
        ----------
        collection_name : str
            Target collection. Must be one of the four canonical names.

        Returns
        -------
        int
        """
        return self.get_collection(collection_name).count()

    @property
    def registered_collections(self) -> tuple[str, ...]:
        """
        Return the names of all registered collections in declaration order.

        Returns
        -------
        tuple[str, ...]
        """
        return ALL_COLLECTIONS
