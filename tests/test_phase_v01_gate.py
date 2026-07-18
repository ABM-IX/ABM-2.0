"""
tests/test_phase_v01_gate.py
============================
Phase v0.1 Memory Brain Core — Gate Test Suite

This file is the hard gate for advancing to Phase v0.2. Every assertion
below must pass 100%. Failures here block v0.2 work.

Proofs required by PROJECT_BRIEF.md / ABM_SPEC.md section 10:
  1. Collection isolation — a document written to one of the four ChromaDB
     collections is never retrievable from any of the other three.
  2. Chunking boundary rules — each stream chunker respects its spec rule.
  3. Embedding consistency — OllamaEmbeddingWrapper returns identical
     vectors for repeated calls with the same input.

Isolation tests use a real in-memory ChromaDB EphemeralClient (no disk,
no Ollama). Embedding consistency uses mocked HTTP so the suite stays
fully offline and deterministic.
"""

from __future__ import annotations

import os
import sys
import unittest
from typing import Any
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from abm.memory.chroma_controller import (
    ALL_COLLECTIONS,
    COLLECTION_AMBIENT_TELEMETRY,
    COLLECTION_CODE_TOPOLOGIES,
    COLLECTION_COGNITIVE_IDENTITY,
    COLLECTION_TECHNICAL_MASTERY,
    ChromaController,
)
from abm.memory.chunking import (
    STREAM_B_TOKEN_OVERLAP,
    STREAM_B_TOKEN_WINDOW,
    STREAM_C_INTERACTION_GAP_SECONDS,
    chunk_stream_a_code_topologies,
    chunk_stream_b_technical_mastery,
    chunk_stream_c_ambient_telemetry,
)
from abm.memory.embedding_wrapper import OllamaEmbeddingWrapper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EMBED_DIM = 32


def _unit_vector(axis: int, dim: int = EMBED_DIM) -> list[float]:
    """One-hot-ish unit vector so nearest-neighbour queries are unambiguous."""
    vec = [0.0] * dim
    vec[axis % dim] = 1.0
    return vec


def _flat_ids(result) -> list[str]:
    """Flatten ChromaDB nested id lists from QueryResult."""
    if not result.ids:
        return []
    flat: list[str] = []
    for group in result.ids:
        flat.extend(group)
    return flat


# Distinct documents + orthogonal embeddings for each collection.
GATE_DOCUMENTS: dict[str, dict[str, Any]] = {
    COLLECTION_COGNITIVE_IDENTITY: {
        "doc_id": "gate_cog_001",
        "text": "FirstMinds identity: local-first Cognitive OS mandate.",
        "metadata": {
            "owner": "ABM",
            "target_entity": "FirstMinds",
            "volatility": "immutable",
        },
        "embedding": _unit_vector(0),
    },
    COLLECTION_CODE_TOPOLOGIES: {
        "doc_id": "gate_code_001",
        "text": "class UserBloc extends Bloc<UserEvent, UserState> {}",
        "metadata": {
            "language": "dart",
            "framework": "flutter",
            "state_pattern": "bloc",
            "naming_convention": "camelCase",
        },
        "embedding": _unit_vector(1),
    },
    COLLECTION_TECHNICAL_MASTERY: {
        "doc_id": "gate_mastery_001",
        "text": "ChromaDB cosine HNSW indexing reference notes.",
        "metadata": {
            "source": "docs_fetch",
            "date_acquired": "2026-07-18",
            "confidence_score": "0.92",
        },
        "embedding": _unit_vector(2),
    },
    COLLECTION_AMBIENT_TELEMETRY: {
        "doc_id": "gate_telem_001",
        "text": "git commit -m 'phase v0.1 gate'",
        "metadata": {
            "epoch_timestamp": 1784370192,
            "active_repository": "smart_transit",
            "device_source": "dynamic_mobile_node",
        },
        "embedding": _unit_vector(3),
    },
}


# ---------------------------------------------------------------------------
# 1. Collection isolation (real in-memory ChromaDB)
# ---------------------------------------------------------------------------


class TestCollectionIsolationGate(unittest.TestCase):
    """
    Prove full isolation across the four ChromaDB collections.

    A document embedded into one collection must be retrievable from that
    collection and never from any of the other three.
    """

    def setUp(self) -> None:
        self.controller = ChromaController(in_memory=True)
        for collection_name, doc in GATE_DOCUMENTS.items():
            self.controller.add_document(
                collection_name,
                doc["doc_id"],
                doc["text"],
                doc["metadata"],
                doc["embedding"],
            )

    def tearDown(self) -> None:
        for name in ALL_COLLECTIONS:
            self.controller.clear_collection(name)

    def test_four_collections_registered(self) -> None:
        self.assertEqual(
            tuple(self.controller.registered_collections),
            ALL_COLLECTIONS,
        )
        self.assertEqual(len(ALL_COLLECTIONS), 4)

    def test_each_collection_holds_exactly_its_own_document(self) -> None:
        for collection_name, doc in GATE_DOCUMENTS.items():
            with self.subTest(collection=collection_name):
                self.assertEqual(self.controller.collection_count(collection_name), 1)
                result = self.controller.query_collection(
                    collection_name,
                    doc["embedding"],
                    n_results=5,
                )
                ids = _flat_ids(result)
                self.assertEqual(ids, [doc["doc_id"]])

    def test_document_never_retrievable_from_other_collections(self) -> None:
        """
        Primary isolation gate: for every source collection, query every
        other collection with that document's embedding — the source
        doc_id must never appear.
        """
        for source_name, doc in GATE_DOCUMENTS.items():
            for target_name in ALL_COLLECTIONS:
                if target_name == source_name:
                    continue
                with self.subTest(source=source_name, queried=target_name):
                    result = self.controller.query_collection(
                        target_name,
                        doc["embedding"],
                        n_results=5,
                    )
                    retrieved = _flat_ids(result)
                    self.assertNotIn(
                        doc["doc_id"],
                        retrieved,
                        f"ISOLATION FAILURE: doc '{doc['doc_id']}' written to "
                        f"'{source_name}' was retrieved from '{target_name}'.",
                    )

    def test_pairwise_write_then_cross_query_all_directions(self) -> None:
        """
        Exhaustive pairwise check: write-only-to-A then query B/C/D yields
        no A doc; repeat for every source.
        """
        # Fresh controller so prior setUp docs do not interfere with
        # single-source write semantics.
        controller = ChromaController(in_memory=True)
        for source_name, doc in GATE_DOCUMENTS.items():
            for name in ALL_COLLECTIONS:
                controller.clear_collection(name)

            controller.add_document(
                source_name,
                doc["doc_id"],
                doc["text"],
                doc["metadata"],
                doc["embedding"],
            )
            self.assertEqual(controller.collection_count(source_name), 1)

            for other_name in ALL_COLLECTIONS:
                if other_name == source_name:
                    continue
                with self.subTest(source=source_name, empty=other_name):
                    self.assertEqual(controller.collection_count(other_name), 0)
                    result = controller.query_collection(
                        other_name,
                        doc["embedding"],
                        n_results=5,
                    )
                    self.assertEqual(
                        _flat_ids(result),
                        [],
                        f"BLEED: '{source_name}' → '{other_name}'",
                    )


# ---------------------------------------------------------------------------
# 2. Chunking boundary rules
# ---------------------------------------------------------------------------


class TestChunkingBoundaryGate(unittest.TestCase):
    """Prove each chunking function respects its spec boundary rule."""

    # ---- Stream A: AST / structural boundaries, never mid-line ----

    def test_stream_a_python_splits_on_ast_node_boundaries(self) -> None:
        code = "\n".join(
            [
                "import os",
                "",
                "class UserBloc:",
                "    def build(self):",
                "        return os.getcwd()",
                "",
                "def helper():",
                "    return True",
            ]
        )
        chunks = chunk_stream_a_code_topologies(code, "python")
        self.assertEqual(len(chunks), 3)
        self.assertTrue(chunks[0].startswith("import os"))
        self.assertTrue(chunks[1].startswith("class UserBloc:"))
        self.assertTrue(chunks[2].startswith("def helper():"))
        # Class chunk must not swallow the following top-level function.
        self.assertNotIn("def helper", chunks[1])

    def test_stream_a_never_splits_mid_line(self) -> None:
        """
        Boundary rule: every chunk edge aligns to a full source line.
        No chunk may contain a truncated mid-line fragment relative to
        the original source lines.
        """
        samples = {
            "python": "\n".join(
                [
                    "x = 1",
                    "def alpha():",
                    "    return 2",
                    "def beta():",
                    "    return 3",
                ]
            ),
            "dart": "\n".join(
                [
                    "class UserBloc {",
                    "  void build() {",
                    "    emit(UserState());",
                    "  }",
                    "}",
                    "class UserState {}",
                ]
            ),
            "kotlin": "\n".join(
                [
                    "class UserBloc {",
                    "  fun build() {",
                    "    emit()",
                    "  }",
                    "}",
                    "class UserState {}",
                ]
            ),
        }
        for language, code in samples.items():
            source_lines = set(code.splitlines())
            chunks = chunk_stream_a_code_topologies(code, language)
            with self.subTest(language=language):
                self.assertGreater(len(chunks), 0)
                for chunk in chunks:
                    for line in chunk.splitlines():
                        self.assertIn(
                            line,
                            source_lines,
                            f"MID-LINE SPLIT in {language}: {line!r} is not a "
                            f"complete source line.",
                        )

    def test_stream_a_dart_and_kotlin_split_on_brace_boundaries(self) -> None:
        dart = "\n".join(
            [
                "class UserBloc {",
                "  void build() {",
                "    emit(UserState());",
                "  }",
                "}",
                "class UserState {}",
            ]
        )
        kotlin = "\n".join(
            [
                "class UserBloc {",
                "  fun build() {",
                "    emit()",
                "  }",
                "}",
                "class UserState {}",
            ]
        )
        dart_chunks = chunk_stream_a_code_topologies(dart, "dart")
        kotlin_chunks = chunk_stream_a_code_topologies(kotlin, "kotlin")
        self.assertEqual(len(dart_chunks), 2)
        self.assertEqual(len(kotlin_chunks), 2)
        self.assertTrue(dart_chunks[0].rstrip().endswith("}"))
        self.assertTrue(kotlin_chunks[0].rstrip().endswith("}"))

    # ---- Stream B: 500-token window, 50-token overlap ----

    def test_stream_b_respects_500_token_window_and_50_token_overlap(self) -> None:
        self.assertEqual(STREAM_B_TOKEN_WINDOW, 500)
        self.assertEqual(STREAM_B_TOKEN_OVERLAP, 50)

        text = " ".join(f"token{i}" for i in range(700))
        chunks = chunk_stream_b_technical_mastery(text)
        self.assertEqual(len(chunks), 2)

        first = chunks[0].split()
        second = chunks[1].split()
        self.assertEqual(len(first), 500)
        # Second window starts at token 450 (step = 500 - 50); 700 - 450 = 250.
        self.assertEqual(len(second), 250)
        self.assertEqual(first[-50:], second[:50])
        self.assertEqual(first[-50:], [f"token{i}" for i in range(450, 500)])

    def test_stream_b_step_is_window_minus_overlap(self) -> None:
        """Adjacent windows advance by 450 tokens (500 - 50)."""
        text = " ".join(f"t{i}" for i in range(1200))
        chunks = chunk_stream_b_technical_mastery(text)
        # starts at 0, 450, 900 → three windows
        self.assertEqual(len(chunks), 3)
        tokens_0 = chunks[0].split()
        tokens_1 = chunks[1].split()
        tokens_2 = chunks[2].split()
        self.assertEqual(len(tokens_0), 500)
        self.assertEqual(len(tokens_1), 500)
        self.assertEqual(len(tokens_2), 300)
        self.assertEqual(tokens_0[450:], tokens_1[:50])
        self.assertEqual(tokens_1[450:], tokens_2[:50])

    # ---- Stream C: chronological windows on 120-second gaps ----

    def test_stream_c_splits_only_when_gap_exceeds_120_seconds(self) -> None:
        self.assertEqual(STREAM_C_INTERACTION_GAP_SECONDS, 120)

        events = [
            {"epoch_timestamp": 240, "active_repository": "smart_transit"},
            {"epoch_timestamp": 0, "active_repository": "smart_transit"},
            {"epoch_timestamp": 120, "active_repository": "smart_transit"},
            {"epoch_timestamp": 361, "active_repository": "houseconnect"},
        ]
        windows = chunk_stream_c_ambient_telemetry(events)
        stamps = [[e["epoch_timestamp"] for e in window] for window in windows]
        # Gaps: 0→120 (=120, keep), 120→240 (=120, keep), 240→361 (=121, split)
        self.assertEqual(stamps, [[0, 120, 240], [361]])

    def test_stream_c_exact_120_second_gap_keeps_events_together(self) -> None:
        events = [
            {"epoch_timestamp": 1000, "active_repository": "smart_transit"},
            {"epoch_timestamp": 1120, "active_repository": "smart_transit"},
            {"epoch_timestamp": 1240, "active_repository": "smart_transit"},
        ]
        windows = chunk_stream_c_ambient_telemetry(events)
        self.assertEqual(len(windows), 1)
        self.assertEqual(len(windows[0]), 3)

    def test_stream_c_121_second_gap_starts_new_window(self) -> None:
        events = [
            {"epoch_timestamp": 1000, "active_repository": "houseconnect"},
            {"epoch_timestamp": 1121, "active_repository": "houseconnect"},
        ]
        windows = chunk_stream_c_ambient_telemetry(events)
        self.assertEqual(len(windows), 2)
        self.assertEqual(windows[0][0]["epoch_timestamp"], 1000)
        self.assertEqual(windows[1][0]["epoch_timestamp"], 1121)


# ---------------------------------------------------------------------------
# 3. Embedding wrapper consistency
# ---------------------------------------------------------------------------


class TestEmbeddingConsistencyGate(unittest.TestCase):
    """
    Prove OllamaEmbeddingWrapper returns consistent vectors for repeated
    calls with the same input text.
    """

    def setUp(self) -> None:
        self.wrapper = OllamaEmbeddingWrapper()
        self.fixed_vector = [float(i) * 0.001 for i in range(768)]

    def _mock_response(self, embedding: list[float]) -> MagicMock:
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"embedding": embedding}
        return response

    @patch("abm.memory.embedding_wrapper.requests.post")
    def test_repeated_embed_calls_return_identical_vectors(self, mock_post) -> None:
        mock_post.return_value = self._mock_response(self.fixed_vector)

        text = "nomic-embed-text consistency probe"
        first = self.wrapper.embed(text)
        second = self.wrapper.embed(text)
        third = self.wrapper.embed(text)

        self.assertEqual(first, second)
        self.assertEqual(second, third)
        self.assertEqual(first, self.fixed_vector)
        self.assertEqual(mock_post.call_count, 3)

    @patch("abm.memory.embedding_wrapper.requests.post")
    def test_embed_batch_is_consistent_with_individual_embeds(self, mock_post) -> None:
        """Batch results for a repeated text match single-call embed()."""
        mock_post.return_value = self._mock_response(self.fixed_vector)
        text = "batch consistency probe"

        solo = self.wrapper.embed(text)
        batch = self.wrapper.embed_batch([text, text])

        self.assertEqual(batch[0], solo)
        self.assertEqual(batch[1], solo)
        self.assertEqual(batch[0], batch[1])

    @patch("abm.memory.embedding_wrapper.requests.post")
    def test_same_prompt_yields_same_vector_across_wrapper_instances(
        self, mock_post
    ) -> None:
        mock_post.return_value = self._mock_response(self.fixed_vector)
        text = "cross-instance consistency"

        a = OllamaEmbeddingWrapper().embed(text)
        b = OllamaEmbeddingWrapper().embed(text)
        self.assertEqual(a, b)

    @patch("abm.memory.embedding_wrapper.requests.post")
    def test_deterministic_model_response_is_passed_through_unchanged(
        self, mock_post
    ) -> None:
        """
        Wrapper must not mutate embedding values — identical upstream
        payloads must surface as bit-identical float lists.
        """
        payload = [0.125, -0.5, 0.0, 1.0] + [0.0] * 764
        mock_post.return_value = self._mock_response(payload)

        v1 = self.wrapper.embed("pass-through check")
        v2 = self.wrapper.embed("pass-through check")
        self.assertIsInstance(v1, list)
        self.assertTrue(all(isinstance(x, float) for x in v1))
        self.assertEqual(v1, payload)
        self.assertEqual(v1, v2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
