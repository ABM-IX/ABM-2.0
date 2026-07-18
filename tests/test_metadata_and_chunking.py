"""
tests/test_metadata_and_chunking.py
===================================
Contract tests for stream metadata validation and chunking.
"""

from __future__ import annotations

import os
import sys
import unittest

from pydantic import ValidationError

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from abm.memory.chunking import (
    STREAM_B_TOKEN_OVERLAP,
    STREAM_B_TOKEN_WINDOW,
    STREAM_C_INTERACTION_GAP_SECONDS,
    chunk_stream_a_code_topologies,
    chunk_stream_b_technical_mastery,
    chunk_stream_c_ambient_telemetry,
)
from abm.memory.metadata_models import (
    AmbientTelemetryMetadata,
    CodeTopologiesMetadata,
    CognitiveIdentityMetadata,
    TechnicalMasteryMetadata,
)


class TestMetadataModels(unittest.TestCase):
    """Verify exact stream metadata field names and value constraints."""

    def test_cognitive_identity_metadata_accepts_exact_schema(self):
        model = CognitiveIdentityMetadata(
            owner="ABM",
            target_entity="FirstMinds",
            volatility="immutable",
        )
        self.assertEqual(model.owner, "ABM")

    def test_cognitive_identity_metadata_rejects_extra_fields(self):
        with self.assertRaises(ValidationError):
            CognitiveIdentityMetadata(
                owner="ABM",
                target_entity="FirstMinds",
                volatility="immutable",
                renamed_field="not_allowed",
            )

    def test_code_topologies_metadata_accepts_exact_schema(self):
        model = CodeTopologiesMetadata(
            language="dart",
            framework="flutter",
            state_pattern="bloc",
            naming_convention="camelCase",
        )
        self.assertEqual(model.language, "dart")

    def test_code_topologies_metadata_rejects_unknown_language(self):
        with self.assertRaises(ValidationError):
            CodeTopologiesMetadata(
                language="javascript",
                framework="flutter",
                state_pattern="bloc",
                naming_convention="camelCase",
            )

    def test_technical_mastery_metadata_accepts_exact_schema(self):
        model = TechnicalMasteryMetadata(
            source="docs_fetch",
            date_acquired="2026-07-18",
            confidence_score="0.92",
        )
        self.assertEqual(model.confidence_score, "0.92")

    def test_technical_mastery_metadata_rejects_invalid_confidence_score(self):
        with self.assertRaises(ValidationError):
            TechnicalMasteryMetadata(
                source="docs_fetch",
                date_acquired="2026-07-18",
                confidence_score="1.92",
            )

    def test_ambient_telemetry_metadata_accepts_exact_schema(self):
        model = AmbientTelemetryMetadata(
            epoch_timestamp=1784370192,
            active_repository="smart_transit",
            device_source="dynamic_mobile_node",
        )
        self.assertEqual(model.device_source, "dynamic_mobile_node")

    def test_ambient_telemetry_metadata_rejects_string_timestamp(self):
        with self.assertRaises(ValidationError):
            AmbientTelemetryMetadata(
                epoch_timestamp="1784370192",
                active_repository="smart_transit",
                device_source="dynamic_mobile_node",
            )


class TestStreamChunking(unittest.TestCase):
    """Verify each stream chunking strategy from ABM_SPEC.md section 3."""

    def test_stream_a_python_chunks_on_ast_boundaries(self):
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
        self.assertTrue(chunks[1].startswith("class UserBloc:"))
        self.assertNotIn("def helper", chunks[1])

    def test_stream_a_dart_chunks_on_closing_brace_lines(self):
        code = "\n".join(
            [
                "class UserBloc {",
                "  void build() {",
                "    emit(UserState());",
                "  }",
                "}",
                "class UserState {}",
            ]
        )
        chunks = chunk_stream_a_code_topologies(code, "dart")
        self.assertEqual(len(chunks), 2)
        self.assertTrue(all("\n" in chunk or chunk.endswith("{}") for chunk in chunks))

    def test_stream_b_uses_500_token_window_and_50_token_overlap(self):
        text = " ".join(f"token{i}" for i in range(700))
        chunks = chunk_stream_b_technical_mastery(text)
        self.assertEqual(STREAM_B_TOKEN_WINDOW, 500)
        self.assertEqual(STREAM_B_TOKEN_OVERLAP, 50)
        self.assertEqual(len(chunks), 2)
        first_tokens = chunks[0].split()
        second_tokens = chunks[1].split()
        self.assertEqual(len(first_tokens), 500)
        self.assertEqual(first_tokens[-50:], second_tokens[:50])

    def test_stream_c_splits_on_120_second_interaction_gaps(self):
        events = [
            {"epoch_timestamp": 240, "active_repository": "smart_transit"},
            {"epoch_timestamp": 0, "active_repository": "smart_transit"},
            {"epoch_timestamp": 120, "active_repository": "smart_transit"},
            {"epoch_timestamp": 361, "active_repository": "smart_transit"},
        ]
        windows = chunk_stream_c_ambient_telemetry(events)
        self.assertEqual(STREAM_C_INTERACTION_GAP_SECONDS, 120)
        self.assertEqual([[event["epoch_timestamp"] for event in window] for window in windows], [[0, 120, 240], [361]])


if __name__ == "__main__":
    unittest.main(verbosity=2)
