"""
abm/api/core/config.py
======================
APIConfig — configuration dataclass for the ABM API layer.

All runtime parameters the API layer and ServiceRegistry need are declared
here. Centralising them in a single dataclass makes the boot sequence
explicit and every value discoverable without grepping module internals.

Design contract:
  - APIConfig is a plain dataclass with no side effects.
  - All path defaults mirror the existing v0.1–v0.5 module constants so
    the system works out-of-the-box from the repo root without extra config.
  - Never import from non-standard library here — this module has zero deps
    on the rest of the abm package so it can be imported at the very top of
    the boot sequence.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class APIConfig:
    """
    Immutable configuration for the ABM API layer.

    Create one instance at startup (e.g. ``APIConfig()`` for defaults) and
    pass it to ``ServiceRegistry``. Do not mutate after boot.

    Parameters
    ----------
    chroma_persist_directory : str
        Filesystem path for ChromaDB's persistent storage.
        Matches the v0.1 ChromaController default.
    ollama_base_url : str
        Local Ollama server base URL. Must always be the loopback address
        per Architectural Constitution rule 1.
    embedding_model : str
        Ollama model used for embeddings. Must match the v0.1 constant.
    classification_model : str
        Ollama model used for task classification. Must match the v0.3
        OllamaModelGateway default (phi3:mini).
    quarantine_dir : str
        Path to the v0.4 ambiguity quarantine directory.
    connect_timeout : float
        TCP connect timeout (seconds) for Ollama HTTP calls.
    read_timeout : float
        HTTP read timeout (seconds) for Ollama HTTP calls.
    n_retrieval_results : int
        Default number of results returned per collection in knowledge
        retrieval operations.
    """

    # --- Persistence ---
    chroma_persist_directory: str = "./memory/chroma_store"

    # --- Ollama (local-only, per constitution rule 1) ---
    ollama_base_url: str = "http://127.0.0.1:11434"
    embedding_model: str = "nomic-embed-text"
    classification_model: str = "phi3:mini"

    # --- Governance ---
    quarantine_dir: str = "memory/ambiguity_quarantine"

    # --- HTTP ---
    connect_timeout: float = 5.0
    read_timeout: float = 30.0

    # --- Retrieval ---
    n_retrieval_results: int = 5


__all__ = ["APIConfig"]
