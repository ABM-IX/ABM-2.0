"""
abm.memory — Quad-Stream High-Density Memory Architecture (spec section 3)

Exports the two primary Phase v0.1 components:
  - ChromaController  : manages the four isolated ChromaDB collections
  - OllamaEmbeddingWrapper : connects to nomic-embed-text via local Ollama
"""

from .chroma_controller import ChromaController
from .chunking import (
    STREAM_B_TOKEN_OVERLAP,
    STREAM_B_TOKEN_WINDOW,
    STREAM_C_INTERACTION_GAP_SECONDS,
    chunk_stream_a_code_topologies,
    chunk_stream_b_technical_mastery,
    chunk_stream_c_ambient_telemetry,
)
from .embedding_wrapper import OllamaEmbeddingWrapper
from .metadata_models import (
    AmbientTelemetryMetadata,
    CodeTopologiesMetadata,
    CognitiveIdentityMetadata,
    TechnicalMasteryMetadata,
)

__all__ = [
    "ChromaController",
    "OllamaEmbeddingWrapper",
    "CognitiveIdentityMetadata",
    "CodeTopologiesMetadata",
    "TechnicalMasteryMetadata",
    "AmbientTelemetryMetadata",
    "STREAM_B_TOKEN_WINDOW",
    "STREAM_B_TOKEN_OVERLAP",
    "STREAM_C_INTERACTION_GAP_SECONDS",
    "chunk_stream_a_code_topologies",
    "chunk_stream_b_technical_mastery",
    "chunk_stream_c_ambient_telemetry",
]
