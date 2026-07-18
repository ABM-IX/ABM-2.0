"""
tests/test_memory_isolation.py
===============================
Phase v0.1 Gate Tests — Zero Data Crossover Between Collections
Spec Reference: ABM_SPEC.md sections 3, 4, and 10

These tests use unittest.mock to prove the isolation contract at the
interface level. No live Ollama server or live ChromaDB instance is
required. The tests mock the underlying ChromaDB client and requests
library so the suite runs fully offline, deterministically, and at speed.

Phase v0.1 does NOT advance to v0.2 until all tests in this file pass 100%.

Test Classes:
  TestCollectionNames        — verifies all four collection names exactly match spec
  TestMetadataSchemas        — verifies each schema has the exact fields from spec section 3
  TestChromeControllerIsolation — proves add_document never routes to wrong collection
  TestQueryIsolation         — proves query_collection returns empty for non-target collections
  TestEmbeddingWrapper       — verifies embed calls reach nomic-embed-text at 127.0.0.1:11434
  TestEmbeddingWrapperErrors — verifies correct errors on bad inputs / unreachable server
  TestCrossCollectionBleed   — combined scenario: write to one, confirm zero bleed to others
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch, call
from typing import Any

# ---------------------------------------------------------------------------
# Absolute imports — adjust sys.path if running from repo root directly
# ---------------------------------------------------------------------------

import sys
import os

# Ensure the repo root is on sys.path so `abm` resolves correctly when
# running: python -m pytest tests/ from the project root.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from abm.memory.chroma_controller import (
    ChromaController,
    ALL_COLLECTIONS,
    COLLECTION_COGNITIVE_IDENTITY,
    COLLECTION_CODE_TOPOLOGIES,
    COLLECTION_TECHNICAL_MASTERY,
    COLLECTION_AMBIENT_TELEMETRY,
    COLLECTION_SCHEMAS,
    SCHEMA_COGNITIVE_IDENTITY,
    SCHEMA_CODE_TOPOLOGIES,
    SCHEMA_TECHNICAL_MASTERY,
    SCHEMA_AMBIENT_TELEMETRY,
    QueryResult,
)
from abm.memory.embedding_wrapper import (
    OllamaEmbeddingWrapper,
    OLLAMA_BASE_URL,
    OLLAMA_EMBED_ENDPOINT,
    EMBEDDING_MODEL,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

# A realistic 768-dim nomic-embed-text vector (mocked as sequential floats)
MOCK_EMBEDDING_DIM = 768
MOCK_EMBEDDING_A: list[float] = [float(i) / MOCK_EMBEDDING_DIM for i in range(MOCK_EMBEDDING_DIM)]
MOCK_EMBEDDING_B: list[float] = [float(i + 1) / MOCK_EMBEDDING_DIM for i in range(MOCK_EMBEDDING_DIM)]
MOCK_EMBEDDING_C: list[float] = [float(i + 2) / MOCK_EMBEDDING_DIM for i in range(MOCK_EMBEDDING_DIM)]
MOCK_EMBEDDING_D: list[float] = [float(i + 3) / MOCK_EMBEDDING_DIM for i in range(MOCK_EMBEDDING_DIM)]

# Sample documents for each stream
DOC_COGNITIVE: dict[str, Any] = {
    "doc_id": "cogid_001",
    "text": "ABM 2.0 operates as a local-first Cognitive OS for First Minds.",
    "metadata": {
        "owner": "ABM",
        "target_entity": "FirstMinds",
        "volatility": "immutable",
    },
    "embedding": MOCK_EMBEDDING_D,
}

DOC_CODE: dict[str, Any] = {
    "doc_id": "code_001",
    "text": "class UserBloc extends Bloc<UserEvent, UserState> {}",
    "metadata": {
        "language": "dart",
        "framework": "flutter",
        "state_pattern": "bloc",
        "naming_convention": "camelCase",
    },
    "embedding": MOCK_EMBEDDING_A,
}

DOC_MASTERY: dict[str, Any] = {
    "doc_id": "mastery_001",
    "text": "ChromaDB v0.5 supports cosine similarity with HNSW indexing.",
    "metadata": {
        "source": "docs_fetch",
        "date_acquired": "2026-07-18",
        "confidence_score": "0.92",
    },
    "embedding": MOCK_EMBEDDING_B,
}

DOC_TELEMETRY: dict[str, Any] = {
    "doc_id": "telem_001",
    "text": "git commit -m 'init: Phase v0.1 Memory Brain Core'",
    "metadata": {
        "epoch_timestamp": 1784370192,
        "active_repository": "smart_transit",
        "device_source": "dynamic_mobile_node",
    },
    "embedding": MOCK_EMBEDDING_C,
}

ALL_DOCS = {
    COLLECTION_COGNITIVE_IDENTITY: DOC_COGNITIVE,
    COLLECTION_CODE_TOPOLOGIES: DOC_CODE,
    COLLECTION_TECHNICAL_MASTERY: DOC_MASTERY,
    COLLECTION_AMBIENT_TELEMETRY: DOC_TELEMETRY,
}


def _make_mock_chroma_client() -> MagicMock:
    """Return a MagicMock that mimics a chromadb.ClientAPI."""
    client = MagicMock()
    # get_or_create_collection returns a per-collection MagicMock
    collection_mocks: dict[str, MagicMock] = {}

    def _get_or_create(name: str, metadata: dict | None = None) -> MagicMock:
        if name not in collection_mocks:
            col = MagicMock()
            col.name = name
            col.count.return_value = 0
            col.get.return_value = {"ids": []}
            collection_mocks[name] = col
        return collection_mocks[name]

    client.get_or_create_collection.side_effect = _get_or_create
    client._collection_mocks = collection_mocks  # expose for assertions
    return client


# ---------------------------------------------------------------------------
# TestCollectionNames
# ---------------------------------------------------------------------------


class TestCollectionNames(unittest.TestCase):
    """Verify all four collection names exactly match spec section 3."""

    def test_collection_name_cognitive_identity(self):
        """Stream D collection name matches spec verbatim."""
        self.assertEqual(COLLECTION_COGNITIVE_IDENTITY, "abm_cognitive_identity")

    def test_collection_name_code_topologies(self):
        """Stream A collection name matches spec verbatim."""
        self.assertEqual(COLLECTION_CODE_TOPOLOGIES, "abm_code_topologies")

    def test_collection_name_technical_mastery(self):
        """Stream B collection name matches spec verbatim."""
        self.assertEqual(COLLECTION_TECHNICAL_MASTERY, "abm_technical_mastery")

    def test_collection_name_ambient_telemetry(self):
        """Stream C collection name matches spec verbatim."""
        self.assertEqual(COLLECTION_AMBIENT_TELEMETRY, "abm_ambient_telemetry")

    def test_all_collections_tuple_contains_exactly_four(self):
        """ALL_COLLECTIONS exports exactly the four spec collections."""
        self.assertEqual(len(ALL_COLLECTIONS), 4)

    def test_all_collections_contains_each_name(self):
        """ALL_COLLECTIONS contains every spec-defined name."""
        for name in (
            "abm_cognitive_identity",
            "abm_code_topologies",
            "abm_technical_mastery",
            "abm_ambient_telemetry",
        ):
            with self.subTest(collection=name):
                self.assertIn(name, ALL_COLLECTIONS)

    def test_no_extra_collections_defined(self):
        """No undocumented collections sneak into ALL_COLLECTIONS."""
        expected = {
            "abm_cognitive_identity",
            "abm_code_topologies",
            "abm_technical_mastery",
            "abm_ambient_telemetry",
        }
        self.assertEqual(set(ALL_COLLECTIONS), expected)


# ---------------------------------------------------------------------------
# TestMetadataSchemas
# ---------------------------------------------------------------------------


class TestMetadataSchemas(unittest.TestCase):
    """
    Verify each metadata schema has the exact fields from spec section 3.
    No renaming, no missing fields, no extra fields.
    """

    # ---- Stream D ----

    def test_cognitive_identity_schema_field_owner(self):
        self.assertIn("owner", SCHEMA_COGNITIVE_IDENTITY)
        self.assertEqual(SCHEMA_COGNITIVE_IDENTITY["owner"], "ABM")

    def test_cognitive_identity_schema_field_target_entity(self):
        self.assertIn("target_entity", SCHEMA_COGNITIVE_IDENTITY)
        self.assertEqual(SCHEMA_COGNITIVE_IDENTITY["target_entity"], "FirstMinds")

    def test_cognitive_identity_schema_field_volatility(self):
        self.assertIn("volatility", SCHEMA_COGNITIVE_IDENTITY)
        self.assertEqual(SCHEMA_COGNITIVE_IDENTITY["volatility"], "immutable")

    def test_cognitive_identity_schema_has_exactly_three_fields(self):
        self.assertEqual(len(SCHEMA_COGNITIVE_IDENTITY), 3)

    # ---- Stream A ----

    def test_code_topologies_schema_field_language(self):
        self.assertIn("language", SCHEMA_CODE_TOPOLOGIES)

    def test_code_topologies_schema_field_framework(self):
        self.assertIn("framework", SCHEMA_CODE_TOPOLOGIES)
        self.assertEqual(SCHEMA_CODE_TOPOLOGIES["framework"], "flutter")

    def test_code_topologies_schema_field_state_pattern(self):
        self.assertIn("state_pattern", SCHEMA_CODE_TOPOLOGIES)
        self.assertEqual(SCHEMA_CODE_TOPOLOGIES["state_pattern"], "bloc")

    def test_code_topologies_schema_field_naming_convention(self):
        self.assertIn("naming_convention", SCHEMA_CODE_TOPOLOGIES)
        self.assertEqual(SCHEMA_CODE_TOPOLOGIES["naming_convention"], "camelCase")

    def test_code_topologies_schema_has_exactly_four_fields(self):
        self.assertEqual(len(SCHEMA_CODE_TOPOLOGIES), 4)

    # ---- Stream B ----

    def test_technical_mastery_schema_field_source(self):
        self.assertIn("source", SCHEMA_TECHNICAL_MASTERY)

    def test_technical_mastery_schema_field_date_acquired(self):
        self.assertIn("date_acquired", SCHEMA_TECHNICAL_MASTERY)
        self.assertEqual(SCHEMA_TECHNICAL_MASTERY["date_acquired"], "2026-07-18")

    def test_technical_mastery_schema_field_confidence_score(self):
        self.assertIn("confidence_score", SCHEMA_TECHNICAL_MASTERY)
        self.assertEqual(SCHEMA_TECHNICAL_MASTERY["confidence_score"], "0.92")

    def test_technical_mastery_schema_has_exactly_three_fields(self):
        self.assertEqual(len(SCHEMA_TECHNICAL_MASTERY), 3)

    # ---- Stream C ----

    def test_ambient_telemetry_schema_field_epoch_timestamp(self):
        self.assertIn("epoch_timestamp", SCHEMA_AMBIENT_TELEMETRY)
        self.assertEqual(SCHEMA_AMBIENT_TELEMETRY["epoch_timestamp"], 1784370192)

    def test_ambient_telemetry_schema_field_active_repository(self):
        self.assertIn("active_repository", SCHEMA_AMBIENT_TELEMETRY)

    def test_ambient_telemetry_schema_field_device_source(self):
        self.assertIn("device_source", SCHEMA_AMBIENT_TELEMETRY)
        # Uses dynamic_mobile_node per spec hardware-agnostic update (section 10 addendum)
        self.assertEqual(SCHEMA_AMBIENT_TELEMETRY["device_source"], "dynamic_mobile_node")

    def test_ambient_telemetry_schema_has_exactly_three_fields(self):
        self.assertEqual(len(SCHEMA_AMBIENT_TELEMETRY), 3)

    # ---- Collection → Schema mapping ----

    def test_collection_schemas_map_covers_all_collections(self):
        """COLLECTION_SCHEMAS maps every spec collection to a schema."""
        for name in ALL_COLLECTIONS:
            with self.subTest(collection=name):
                self.assertIn(name, COLLECTION_SCHEMAS)

    def test_collection_schemas_map_has_no_extra_keys(self):
        """COLLECTION_SCHEMAS contains no undocumented collection mappings."""
        self.assertEqual(set(COLLECTION_SCHEMAS.keys()), set(ALL_COLLECTIONS))


# ---------------------------------------------------------------------------
# TestChromeControllerIsolation
# ---------------------------------------------------------------------------


class TestChromeControllerIsolation(unittest.TestCase):
    """
    Prove that ChromaController.add_document routes to the correct underlying
    ChromaDB collection and never to any other collection.
    """

    def setUp(self):
        patcher = patch("abm.memory.chroma_controller.chromadb")
        self.mock_chromadb = patcher.start()
        self.addCleanup(patcher.stop)

        self.mock_client = _make_mock_chroma_client()
        self.mock_chromadb.EphemeralClient.return_value = self.mock_client
        self.mock_chromadb.PersistentClient.return_value = self.mock_client

        self.controller = ChromaController(in_memory=True)

    def _get_collection_mock(self, name: str) -> MagicMock:
        return self.mock_client._collection_mocks[name]

    def test_initialize_collections_calls_get_or_create_for_all_four(self):
        """All four collections are registered on init."""
        called_names = [
            c[1]["name"] if "name" in c[1] else c[0][0]
            for c in self.mock_client.get_or_create_collection.call_args_list
        ]
        # Flatten: keyword vs positional
        actual_names = []
        for c in self.mock_client.get_or_create_collection.call_args_list:
            args, kwargs = c
            actual_names.append(kwargs.get("name") or args[0])

        for expected in ALL_COLLECTIONS:
            with self.subTest(collection=expected):
                self.assertIn(expected, actual_names)

    def test_add_document_routes_to_cognitive_identity_only(self):
        """Writing to abm_cognitive_identity does NOT touch other collections."""
        doc = DOC_COGNITIVE
        self.controller.add_document(
            COLLECTION_COGNITIVE_IDENTITY,
            doc["doc_id"], doc["text"], doc["metadata"], doc["embedding"],
        )
        # Target collection received the upsert
        target_col = self._get_collection_mock(COLLECTION_COGNITIVE_IDENTITY)
        target_col.upsert.assert_called_once()

        # All other collections received NO upsert
        for other in ALL_COLLECTIONS:
            if other == COLLECTION_COGNITIVE_IDENTITY:
                continue
            with self.subTest(other_collection=other):
                other_col = self._get_collection_mock(other)
                other_col.upsert.assert_not_called()

    def test_add_document_routes_to_code_topologies_only(self):
        """Writing to abm_code_topologies does NOT touch other collections."""
        doc = DOC_CODE
        self.controller.add_document(
            COLLECTION_CODE_TOPOLOGIES,
            doc["doc_id"], doc["text"], doc["metadata"], doc["embedding"],
        )
        target_col = self._get_collection_mock(COLLECTION_CODE_TOPOLOGIES)
        target_col.upsert.assert_called_once()

        for other in ALL_COLLECTIONS:
            if other == COLLECTION_CODE_TOPOLOGIES:
                continue
            with self.subTest(other_collection=other):
                other_col = self._get_collection_mock(other)
                other_col.upsert.assert_not_called()

    def test_add_document_routes_to_technical_mastery_only(self):
        """Writing to abm_technical_mastery does NOT touch other collections."""
        doc = DOC_MASTERY
        self.controller.add_document(
            COLLECTION_TECHNICAL_MASTERY,
            doc["doc_id"], doc["text"], doc["metadata"], doc["embedding"],
        )
        target_col = self._get_collection_mock(COLLECTION_TECHNICAL_MASTERY)
        target_col.upsert.assert_called_once()

        for other in ALL_COLLECTIONS:
            if other == COLLECTION_TECHNICAL_MASTERY:
                continue
            with self.subTest(other_collection=other):
                other_col = self._get_collection_mock(other)
                other_col.upsert.assert_not_called()

    def test_add_document_routes_to_ambient_telemetry_only(self):
        """Writing to abm_ambient_telemetry does NOT touch other collections."""
        doc = DOC_TELEMETRY
        self.controller.add_document(
            COLLECTION_AMBIENT_TELEMETRY,
            doc["doc_id"], doc["text"], doc["metadata"], doc["embedding"],
        )
        target_col = self._get_collection_mock(COLLECTION_AMBIENT_TELEMETRY)
        target_col.upsert.assert_called_once()

        for other in ALL_COLLECTIONS:
            if other == COLLECTION_AMBIENT_TELEMETRY:
                continue
            with self.subTest(other_collection=other):
                other_col = self._get_collection_mock(other)
                other_col.upsert.assert_not_called()

    def test_add_document_invalid_collection_raises_value_error(self):
        """add_document raises ValueError for unknown collection names."""
        with self.assertRaises(ValueError) as ctx:
            self.controller.add_document(
                "abm_nonexistent_collection",
                "id_x", "text", {}, [0.1, 0.2],
            )
        self.assertIn("abm_nonexistent_collection", str(ctx.exception))

    def test_get_collection_raises_for_unknown_name(self):
        """get_collection raises ValueError for any name not in spec."""
        with self.assertRaises(ValueError):
            self.controller.get_collection("some_rogue_collection")

    def test_registered_collections_property_matches_all_collections(self):
        """registered_collections returns exactly the spec-defined tuple."""
        self.assertEqual(self.controller.registered_collections, ALL_COLLECTIONS)

    def test_upsert_payload_contains_correct_doc_id(self):
        """The doc_id passed to add_document is preserved in the upsert call."""
        doc = DOC_CODE
        self.controller.add_document(
            COLLECTION_CODE_TOPOLOGIES,
            doc["doc_id"], doc["text"], doc["metadata"], doc["embedding"],
        )
        col = self._get_collection_mock(COLLECTION_CODE_TOPOLOGIES)
        _, kwargs = col.upsert.call_args
        self.assertIn(doc["doc_id"], kwargs["ids"])

    def test_upsert_payload_contains_correct_embedding(self):
        """The embedding passed to add_document is preserved in the upsert call."""
        doc = DOC_MASTERY
        self.controller.add_document(
            COLLECTION_TECHNICAL_MASTERY,
            doc["doc_id"], doc["text"], doc["metadata"], doc["embedding"],
        )
        col = self._get_collection_mock(COLLECTION_TECHNICAL_MASTERY)
        _, kwargs = col.upsert.call_args
        self.assertIn(doc["embedding"], kwargs["embeddings"])

    def test_upsert_payload_contains_correct_metadata(self):
        """The metadata dict passed to add_document appears in the upsert call."""
        doc = DOC_TELEMETRY
        self.controller.add_document(
            COLLECTION_AMBIENT_TELEMETRY,
            doc["doc_id"], doc["text"], doc["metadata"], doc["embedding"],
        )
        col = self._get_collection_mock(COLLECTION_AMBIENT_TELEMETRY)
        _, kwargs = col.upsert.call_args
        self.assertIn(doc["metadata"], kwargs["metadatas"])


# ---------------------------------------------------------------------------
# TestQueryIsolation
# ---------------------------------------------------------------------------


class TestQueryIsolation(unittest.TestCase):
    """
    Prove that query_collection only invokes .query() on the target collection
    and returns empty QueryResult for collections with no data.
    """

    def setUp(self):
        patcher = patch("abm.memory.chroma_controller.chromadb")
        self.mock_chromadb = patcher.start()
        self.addCleanup(patcher.stop)

        self.mock_client = _make_mock_chroma_client()
        self.mock_chromadb.EphemeralClient.return_value = self.mock_client
        self.mock_chromadb.PersistentClient.return_value = self.mock_client

        self.controller = ChromaController(in_memory=True)

    def _get_collection_mock(self, name: str) -> MagicMock:
        return self.mock_client._collection_mocks[name]

    def test_query_empty_collection_returns_empty_query_result(self):
        """Querying an empty collection returns a QueryResult with no results."""
        result = self.controller.query_collection(
            COLLECTION_CODE_TOPOLOGIES, MOCK_EMBEDDING_A
        )
        self.assertIsInstance(result, QueryResult)
        self.assertEqual(result.collection_name, COLLECTION_CODE_TOPOLOGIES)
        self.assertEqual(result.ids, [])
        self.assertEqual(result.documents, [])

    def test_query_only_calls_query_on_target_collection(self):
        """query_collection never calls .query() on non-target collections."""
        # Give the target collection one document so query is actually invoked
        target_col = self._get_collection_mock(COLLECTION_TECHNICAL_MASTERY)
        target_col.count.return_value = 1
        target_col.query.return_value = {
            "ids": [["mastery_001"]],
            "documents": [["Some technical doc"]],
            "metadatas": [[{"source": "docs_fetch", "date_acquired": "2026-07-18", "confidence_score": "0.92"}]],
            "distances": [[0.12]],
        }

        self.controller.query_collection(
            COLLECTION_TECHNICAL_MASTERY, MOCK_EMBEDDING_B
        )

        # Target was queried
        target_col.query.assert_called_once()

        # Every other collection was NOT queried
        for other in ALL_COLLECTIONS:
            if other == COLLECTION_TECHNICAL_MASTERY:
                continue
            with self.subTest(other_collection=other):
                other_col = self._get_collection_mock(other)
                other_col.query.assert_not_called()

    def test_query_result_collection_name_matches_target(self):
        """QueryResult.collection_name reflects the requested collection."""
        result = self.controller.query_collection(
            COLLECTION_AMBIENT_TELEMETRY, MOCK_EMBEDDING_C
        )
        self.assertEqual(result.collection_name, COLLECTION_AMBIENT_TELEMETRY)

    def test_all_empty_collections_return_no_bleed(self):
        """
        Querying each of the four empty collections returns empty results
        across all four — confirming zero-bleed in a clean state.
        """
        query_vec = MOCK_EMBEDDING_A
        for name in ALL_COLLECTIONS:
            with self.subTest(collection=name):
                result = self.controller.query_collection(name, query_vec)
                self.assertEqual(result.ids, [], f"Expected empty ids from {name}")
                self.assertEqual(result.documents, [], f"Expected empty docs from {name}")


# ---------------------------------------------------------------------------
# TestEmbeddingWrapper
# ---------------------------------------------------------------------------


class TestEmbeddingWrapper(unittest.TestCase):
    """
    Verify that OllamaEmbeddingWrapper routes to nomic-embed-text at
    127.0.0.1:11434 — never to any cloud provider.
    """

    def setUp(self):
        self.wrapper = OllamaEmbeddingWrapper()

    def test_default_base_url_is_local_loopback(self):
        """Default base URL must be 127.0.0.1:11434 (spec section 4 mandate)."""
        self.assertEqual(self.wrapper.base_url, "http://127.0.0.1:11434")

    def test_default_model_is_nomic_embed_text(self):
        """Default model must be nomic-embed-text (spec section 4)."""
        self.assertEqual(self.wrapper.model, "nomic-embed-text")

    def test_embed_endpoint_derived_from_base_url(self):
        """embed_endpoint is /api/embeddings on the configured base."""
        self.assertEqual(
            self.wrapper.embed_endpoint, "http://127.0.0.1:11434/api/embeddings"
        )

    def test_module_constant_ollama_base_url(self):
        """Module-level OLLAMA_BASE_URL constant is the local loopback address."""
        self.assertEqual(OLLAMA_BASE_URL, "http://127.0.0.1:11434")

    def test_module_constant_ollama_embed_endpoint(self):
        """Module-level endpoint constant targets the correct Ollama path."""
        self.assertEqual(
            OLLAMA_EMBED_ENDPOINT, "http://127.0.0.1:11434/api/embeddings"
        )

    def test_module_constant_embedding_model(self):
        """Module-level EMBEDDING_MODEL is nomic-embed-text."""
        self.assertEqual(EMBEDDING_MODEL, "nomic-embed-text")

    @patch("abm.memory.embedding_wrapper.requests.post")
    def test_embed_sends_post_to_correct_endpoint(self, mock_post):
        """embed() sends POST to 127.0.0.1:11434/api/embeddings."""
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"embedding": MOCK_EMBEDDING_A},
        )
        self.wrapper.embed("Test input text")
        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        self.assertEqual(call_url, "http://127.0.0.1:11434/api/embeddings")

    @patch("abm.memory.embedding_wrapper.requests.post")
    def test_embed_sends_correct_model_in_payload(self, mock_post):
        """embed() sends model=nomic-embed-text in the POST body."""
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"embedding": MOCK_EMBEDDING_A},
        )
        self.wrapper.embed("some text")
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["model"], "nomic-embed-text")

    @patch("abm.memory.embedding_wrapper.requests.post")
    def test_embed_sends_prompt_in_payload(self, mock_post):
        """embed() puts the input text under the 'prompt' key."""
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"embedding": MOCK_EMBEDDING_A},
        )
        self.wrapper.embed("Flutter BLoC architecture example")
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["prompt"], "Flutter BLoC architecture example")

    @patch("abm.memory.embedding_wrapper.requests.post")
    def test_embed_returns_float_list(self, mock_post):
        """embed() returns the embedding as a list of floats."""
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"embedding": MOCK_EMBEDDING_A},
        )
        result = self.wrapper.embed("nomic embed test")
        self.assertIsInstance(result, list)
        self.assertTrue(all(isinstance(v, float) for v in result))

    @patch("abm.memory.embedding_wrapper.requests.post")
    def test_embed_batch_calls_embed_once_per_text(self, mock_post):
        """embed_batch() invokes the endpoint once for each input text."""
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"embedding": MOCK_EMBEDDING_A},
        )
        texts = ["doc one", "doc two", "doc three"]
        results = self.wrapper.embed_batch(texts)
        self.assertEqual(mock_post.call_count, len(texts))
        self.assertEqual(len(results), len(texts))

    @patch("abm.memory.embedding_wrapper.requests.get")
    def test_health_check_hits_api_tags_endpoint(self, mock_get):
        """health_check() GETs /api/tags on the local Ollama server."""
        mock_get.return_value = MagicMock(status_code=200)
        self.wrapper.health_check()
        call_url = mock_get.call_args[0][0]
        self.assertIn("127.0.0.1:11434", call_url)
        self.assertIn("/api/tags", call_url)

    @patch("abm.memory.embedding_wrapper.requests.get")
    def test_health_check_returns_true_on_200(self, mock_get):
        """health_check() returns True when Ollama responds HTTP 200."""
        mock_get.return_value = MagicMock(status_code=200)
        self.assertTrue(self.wrapper.health_check())

    @patch("abm.memory.embedding_wrapper.requests.get")
    def test_health_check_returns_false_on_non_200(self, mock_get):
        """health_check() returns False on non-200 status codes."""
        mock_get.return_value = MagicMock(status_code=503)
        self.assertFalse(self.wrapper.health_check())

    @patch("abm.memory.embedding_wrapper.requests.get")
    def test_health_check_returns_false_on_connection_error(self, mock_get):
        """health_check() returns False when server is unreachable."""
        import requests as req_lib
        mock_get.side_effect = req_lib.ConnectionError("Connection refused")
        self.assertFalse(self.wrapper.health_check())


# ---------------------------------------------------------------------------
# TestEmbeddingWrapperErrors
# ---------------------------------------------------------------------------


class TestEmbeddingWrapperErrors(unittest.TestCase):
    """Verify correct error types on bad inputs and unreachable server."""

    def setUp(self):
        self.wrapper = OllamaEmbeddingWrapper()

    def test_embed_raises_value_error_on_empty_string(self):
        """embed() raises ValueError when text is empty string."""
        with self.assertRaises(ValueError):
            self.wrapper.embed("")

    def test_embed_raises_value_error_on_whitespace_only(self):
        """embed() raises ValueError when text is whitespace only."""
        with self.assertRaises(ValueError):
            self.wrapper.embed("   ")

    @patch("abm.memory.embedding_wrapper.requests.post")
    def test_embed_raises_connection_error_when_server_down(self, mock_post):
        """embed() raises ConnectionError when Ollama is unreachable."""
        import requests as req_lib
        mock_post.side_effect = req_lib.ConnectionError("Connection refused")
        with self.assertRaises(ConnectionError):
            self.wrapper.embed("some text")

    @patch("abm.memory.embedding_wrapper.requests.post")
    def test_embed_raises_runtime_error_on_non_200(self, mock_post):
        """embed() raises RuntimeError on non-200 HTTP status."""
        mock_post.return_value = MagicMock(status_code=404, text="Not Found")
        with self.assertRaises(RuntimeError):
            self.wrapper.embed("some text")

    @patch("abm.memory.embedding_wrapper.requests.post")
    def test_embed_raises_runtime_error_on_malformed_response(self, mock_post):
        """embed() raises RuntimeError when Ollama returns no 'embedding' key."""
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"error": "model not found"},
        )
        with self.assertRaises(RuntimeError):
            self.wrapper.embed("some text")

    def test_embed_batch_raises_value_error_on_empty_list(self):
        """embed_batch() raises ValueError when texts list is empty."""
        with self.assertRaises(ValueError):
            self.wrapper.embed_batch([])


# ---------------------------------------------------------------------------
# TestCrossCollectionBleed  (combined end-to-end isolation scenario)
# ---------------------------------------------------------------------------


class TestCrossCollectionBleed(unittest.TestCase):
    """
    Combined scenario: write a document to each collection independently,
    then assert zero bleed — documents from one collection never appear in
    any other collection's query results.

    This is the primary v0.1 gate test.
    """

    def setUp(self):
        patcher = patch("abm.memory.chroma_controller.chromadb")
        self.mock_chromadb = patcher.start()
        self.addCleanup(patcher.stop)

        self.mock_client = _make_mock_chroma_client()
        self.mock_chromadb.EphemeralClient.return_value = self.mock_client
        self.mock_chromadb.PersistentClient.return_value = self.mock_client

        self.controller = ChromaController(in_memory=True)

    def _get_collection_mock(self, name: str) -> MagicMock:
        return self.mock_client._collection_mocks[name]

    def test_four_simultaneous_writes_have_no_crossover(self):
        """
        Write one document to each of the four collections simultaneously.
        Assert that each collection received exactly one upsert and no
        other collection received any upsert at all.
        """
        for col_name, doc in ALL_DOCS.items():
            self.controller.add_document(
                col_name,
                doc["doc_id"],
                doc["text"],
                doc["metadata"],
                doc["embedding"],
            )

        for col_name in ALL_COLLECTIONS:
            with self.subTest(collection=col_name):
                col_mock = self._get_collection_mock(col_name)
                # Exactly one write to this collection
                self.assertEqual(
                    col_mock.upsert.call_count,
                    1,
                    f"Collection '{col_name}' should have exactly 1 upsert, "
                    f"got {col_mock.upsert.call_count}.",
                )

    def test_doc_id_written_to_correct_collection_only(self):
        """
        Each doc_id appears in the upsert call for its target collection only.
        Other collections' upsert calls (if any) never include the doc_id.
        """
        for col_name, doc in ALL_DOCS.items():
            self.controller.add_document(
                col_name,
                doc["doc_id"],
                doc["text"],
                doc["metadata"],
                doc["embedding"],
            )

        for target_col, doc in ALL_DOCS.items():
            target_mock = self._get_collection_mock(target_col)
            _, kwargs = target_mock.upsert.call_args
            with self.subTest(doc_id=doc["doc_id"], target=target_col):
                self.assertIn(
                    doc["doc_id"],
                    kwargs["ids"],
                    f"doc_id '{doc['doc_id']}' must appear in '{target_col}' upsert.",
                )

            # Confirm the doc_id does NOT appear in any other collection's upsert
            for other_col in ALL_COLLECTIONS:
                if other_col == target_col:
                    continue
                other_mock = self._get_collection_mock(other_col)
                if other_mock.upsert.call_count == 0:
                    continue  # not called at all — definitely no bleed
                _, other_kwargs = other_mock.upsert.call_args
                with self.subTest(doc_id=doc["doc_id"], wrong_collection=other_col):
                    self.assertNotIn(
                        doc["doc_id"],
                        other_kwargs["ids"],
                        f"CROSSOVER DETECTED: doc_id '{doc['doc_id']}' from "
                        f"'{target_col}' found in '{other_col}' upsert!",
                    )

    def test_query_on_empty_collection_produces_no_bleed(self):
        """
        After writing to abm_code_topologies only, querying the other three
        empty collections returns no results — no data from code_topologies
        bleeds into their results.
        """
        # Write only to Stream A
        doc = DOC_CODE
        self.controller.add_document(
            COLLECTION_CODE_TOPOLOGIES,
            doc["doc_id"], doc["text"], doc["metadata"], doc["embedding"],
        )

        # Query all other collections — they must return empty
        for other in ALL_COLLECTIONS:
            if other == COLLECTION_CODE_TOPOLOGIES:
                continue
            with self.subTest(queried_empty_collection=other):
                result = self.controller.query_collection(other, MOCK_EMBEDDING_A)
                self.assertEqual(
                    result.ids,
                    [],
                    f"BLEED DETECTED: '{COLLECTION_CODE_TOPOLOGIES}' data "
                    f"appeared in '{other}' query results!",
                )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
