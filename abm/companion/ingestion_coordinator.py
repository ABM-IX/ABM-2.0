"""
abm/companion/ingestion_coordinator.py
========================================
Ingestion Coordinator — Phase v0.2 Developer Companion Node
Spec Reference: ABM_SPEC.md sections 3 and 10 (item 2)

The single point of entry that wires FileChangeEvent and GitPipeline outputs
into the v0.1 ChromaController and OllamaEmbeddingWrapper.

Design contract:
  - This is the ONLY class in v0.2 that calls ChromaController.add_document().
    No other v0.2 module touches the database directly.
  - File changes for code files → Stream A (abm_code_topologies).
  - File changes for non-code files → Stream C (abm_ambient_telemetry).
  - Git commits → Stream A (added code chunks) + Stream C (one telemetry event).
  - Streams B and D are never written by this coordinator.
  - All metadata dicts are built to match the exact v0.1 schemas from spec
    section 3. No new fields are invented.
  - IngestionResult.status is "ok", "skipped", or "error". The coordinator
    never raises — it always returns a result, logging errors internally.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from datetime import datetime
from dataclasses import dataclass, field

import pypdf
from pathlib import Path
from typing import Any

from abm.api.core.interfaces import EmbedderInterface, VectorStoreInterface
from abm.memory.chroma_controller import (
    COLLECTION_AMBIENT_TELEMETRY,
    COLLECTION_CODE_TOPOLOGIES,
    COLLECTION_TECHNICAL_MASTERY,
)
from abm.memory.chunking import (
    chunk_stream_a_code_topologies,
    chunk_stream_b_technical_mastery,
    chunk_stream_c_ambient_telemetry,
)

from .file_watcher import CODE_EXTENSIONS, DEVICE_SOURCE, FileChangeEvent, _is_excluded
from .git_pipeline import DEFAULT_MAX_COMMITS, GitPipeline
from .style_fingerprint import StyleExtractionError, StyleFingerprintExtractor

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Languages supported by chunk_stream_a_code_topologies.
_CHUNKABLE_LANGUAGES: frozenset[str] = frozenset({"python", "dart", "kotlin"})

#: Map extension → language for file-change ingestion.
_EXT_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".dart": "dart",
    ".kt": "kotlin",
    ".java": "kotlin",
    ".js": "python",
    ".html": "python",
    ".css": "python",
}


# ---------------------------------------------------------------------------
# IngestionResult
# ---------------------------------------------------------------------------


@dataclass
class IngestionResult:
    """
    The outcome of a single ingestion operation.

    Attributes
    ----------
    status : str
        One of ``"ok"``, ``"skipped"``, ``"error"``.
    collection : str
        The collection that was written to, or that was attempted.
    doc_ids : list[str]
        IDs of documents successfully written. Empty on ``"skipped"``/``"error"``.
    reason : str
        Human-readable explanation. Populated on ``"skipped"`` and ``"error"``.
        Empty on ``"ok"``.
    """

    status: str
    collection: str
    doc_ids: list[str] = field(default_factory=list)
    reason: str = ""


# ---------------------------------------------------------------------------
# IngestionCoordinator
# ---------------------------------------------------------------------------


class IngestionCoordinator:
    """
    Coordinates file-change and Git commit data into the v0.1 memory controller.

    Parameters
    ----------
    controller : ChromaController
        The v0.1 ChromaDB controller. This is the only object that writes to
        ChromaDB — all v0.2 components produce data, not writes.
    embedder : OllamaEmbeddingWrapper
        The v0.1 Ollama embedding wrapper. All embeddings route through
        ``127.0.0.1:11434`` using ``nomic-embed-text``.
    git_pipeline : GitPipeline | None
        Optional Git pipeline for commit-based ingestion. If ``None``,
        ``ingest_git_commit`` and ``ingest_git_tree`` will return skipped results.
    """

    def __init__(
        self,
        controller: VectorStoreInterface,
        embedder: EmbedderInterface,
        git_pipeline: GitPipeline | None = None,
    ) -> None:
        self._controller = controller
        self._embedder = embedder
        self._git = git_pipeline
        self._extractor = StyleFingerprintExtractor()

    # ------------------------------------------------------------------
    # Manual ingestion
    # ------------------------------------------------------------------

    def ingest_document(self, path: str) -> list[IngestionResult]:
        """
        Manually ingest a file or directory.
        Code files go to Stream A.
        General documents (.md, .txt, .pdf) go to Stream B.
        """
        p = Path(path)
        if not p.exists():
            return [IngestionResult(status="error", collection="", reason=f"Path not found: {path}")]
        if _is_excluded(path):
            return [IngestionResult(status="skipped", collection="", reason=f"Path excluded: {path}")]
            
        if p.is_dir():
            results = []
            for root, dirs, files in os.walk(p):
                # Filter exclusions
                dirs[:] = [d for d in dirs if not _is_excluded(d)]
                for file in files:
                    file_path = os.path.join(root, file)
                    if not _is_excluded(file_path):
                        results.extend(self.ingest_document(file_path))
            return results

        ext = p.suffix.lower()
        if ext in CODE_EXTENSIONS:
            # Route to Stream A via _ingest_code_file
            event = FileChangeEvent(
                event_type="modified",
                path=str(p),
                epoch_timestamp=int(time.time()),
                repository="manual_ingest"
            )
            return [self._ingest_code_file(event)]
            
        elif ext in {".txt", ".md", ".pdf"}:
            return [self._ingest_general_document(p, ext)]
            
        else:
            return [IngestionResult(status="skipped", collection="", reason=f"Unsupported file type for manual ingestion: {ext}")]

    def _ingest_general_document(self, p: Path, ext: str) -> IngestionResult:
        try:
            if ext == ".pdf":
                reader = pypdf.PdfReader(str(p))
                text = "\n".join(page.extract_text() or "" for page in reader.pages)
            else:
                text = p.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            return IngestionResult(status="error", collection=COLLECTION_TECHNICAL_MASTERY, reason=f"Failed to read {p.name}: {exc}")
            
        if not text.strip():
            return IngestionResult(status="skipped", collection=COLLECTION_TECHNICAL_MASTERY, reason=f"File is empty: {p.name}")
            
        try:
            chunks = chunk_stream_b_technical_mastery(text)
        except Exception as exc:
            return IngestionResult(status="error", collection=COLLECTION_TECHNICAL_MASTERY, reason=f"Failed to chunk {p.name}: {exc}")

        written_ids = []
        for i, chunk in enumerate(chunks):
            if len(chunk) > 32000:
                logger.warning("_ingest_general_document: chunk %d for '%s' exceeds 32000 chars and will be skipped.", i, p.name)
                continue
            doc_id = self._doc_id(f"manual:{p.name}:{i}", chunk)
            try:
                metadata = {
                    "source": "docs_fetch",
                    "date_acquired": datetime.now().date().isoformat(),
                    "confidence_score": "1.0"
                }
                embedding = self._embedder.embed(chunk)
                self._controller.add_document(
                    COLLECTION_TECHNICAL_MASTERY,
                    doc_id=doc_id,
                    text=chunk,
                    metadata=metadata,
                    embedding=embedding,
                )
                written_ids.append(doc_id)
            except Exception as exc:
                logger.warning("_ingest_general_document: chunk %d failed for '%s': %s", i, p.name, exc)
                
        return IngestionResult(
            status="ok" if written_ids else "skipped",
            collection=COLLECTION_TECHNICAL_MASTERY,
            doc_ids=written_ids,
            reason="" if written_ids else f"No chunks produced from: {p.name}"
        )

    # ------------------------------------------------------------------
    # File-change ingestion
    # ------------------------------------------------------------------

    def ingest_file_change(self, event: FileChangeEvent) -> IngestionResult:
        """
        Process a single ``FileChangeEvent`` from the file watcher.

        Code files (matching ``CODE_EXTENSIONS``) are chunked and written to
        Stream A. Non-code files are logged as a single telemetry event in
        Stream C. Deleted files produce a skipped result — there is nothing
        to embed.

        Parameters
        ----------
        event : FileChangeEvent
            Event produced by ``WorkspaceFileWatcher``.

        Returns
        -------
        IngestionResult
            Never raises; errors are captured in ``IngestionResult.status``.
        """
        if event.event_type == "deleted":
            return IngestionResult(
                status="skipped",
                collection=COLLECTION_CODE_TOPOLOGIES if event.is_code_file
                           else COLLECTION_AMBIENT_TELEMETRY,
                reason=f"Deleted file — nothing to embed: {event.path}",
            )

        if event.is_code_file:
            return self._ingest_code_file(event)
        else:
            return self._ingest_telemetry_event(event)

    # ------------------------------------------------------------------
    # Git ingestion
    # ------------------------------------------------------------------

    def ingest_git_commit(
        self,
        commit_sha: str,
        language: str,
    ) -> IngestionResult:
        """
        Ingest the code changes from a single Git commit into Stream A and
        log a telemetry event into Stream C.

        Calls ``GitPipeline.get_commit_file_chunks()`` (which internally uses
        the v0.1 ``chunk_stream_a_code_topologies`` — not reimplemented here)
        and ``GitPipeline.get_commit_telemetry_event()``.

        Parameters
        ----------
        commit_sha : str
            Full or abbreviated commit SHA.
        language : str
            Language to filter code chunks by. One of ``"dart"``,
            ``"kotlin"``, ``"python"``.

        Returns
        -------
        IngestionResult
            Reports how many Stream A chunks and one Stream C event were written.
            Never raises.
        """
        if self._git is None:
            return IngestionResult(
                status="skipped",
                collection=COLLECTION_CODE_TOPOLOGIES,
                reason="No GitPipeline configured on this IngestionCoordinator.",
            )

        try:
            chunks = self._git.get_commit_file_chunks(commit_sha, language)
            telemetry = self._git.get_commit_telemetry_event(commit_sha)
        except Exception as exc:
            logger.error("ingest_git_commit: failed to read commit '%s': %s", commit_sha, exc)
            return IngestionResult(
                status="error",
                collection=COLLECTION_CODE_TOPOLOGIES,
                reason=str(exc),
            )

        written_ids: list[str] = []

        # --- Stream A: code chunks ---
        for i, chunk in enumerate(chunks):
            if len(chunk) > 32000:
                logger.warning("ingest_git_commit: chunk %d/%d for commit '%s' exceeds 32000 chars and will be skipped.", i + 1, len(chunks), commit_sha[:8])
                continue
            doc_id = self._doc_id(f"git:{commit_sha[:8]}:{language}:{i}", chunk)
            try:
                fp = self._extractor.extract(chunk, language)
                metadata = self._extractor.to_stream_a_metadata(fp)
                embedding = self._embedder.embed(chunk)
                self._controller.add_document(
                    COLLECTION_CODE_TOPOLOGIES,
                    doc_id=doc_id,
                    text=chunk,
                    metadata=metadata,
                    embedding=embedding,
                )
                written_ids.append(doc_id)
            except Exception as exc:
                logger.warning(
                    "ingest_git_commit: chunk %d/%d failed — %s", i + 1, len(chunks), exc
                )

        # --- Stream C: commit telemetry event ---
        self._write_telemetry_event(
            text=telemetry["text"],
            epoch_timestamp=telemetry["epoch_timestamp"],
            active_repository=telemetry["active_repository"],
            context_suffix=f"commit:{commit_sha[:8]}",
        )

        return IngestionResult(
            status="ok" if written_ids or not chunks else "skipped",
            collection=COLLECTION_CODE_TOPOLOGIES,
            doc_ids=written_ids,
            reason="" if written_ids else "No chunkable code found in this commit.",
        )

    def ingest_git_tree(
        self,
        language: str,
        max_commits: int = DEFAULT_MAX_COMMITS,
    ) -> list[IngestionResult]:
        """
        Ingest the last ``max_commits`` commits from HEAD into Stream A and C.

        Intended for first-run bootstrap. Calls ``ingest_git_commit()``
        for each commit, so the v0.1 boundary is respected consistently.

        Parameters
        ----------
        language : str
            Language filter for code chunks.
        max_commits : int
            Maximum number of commits to process. Defaults to ``50``.

        Returns
        -------
        list[IngestionResult]
            One result per commit, in reverse-chronological order.
        """
        if self._git is None:
            return [
                IngestionResult(
                    status="skipped",
                    collection=COLLECTION_CODE_TOPOLOGIES,
                    reason="No GitPipeline configured on this IngestionCoordinator.",
                )
            ]

        try:
            commits = self._git.list_commits(max_count=max_commits)
        except Exception as exc:
            logger.error("ingest_git_tree: failed to list commits — %s", exc)
            return [
                IngestionResult(
                    status="error",
                    collection=COLLECTION_CODE_TOPOLOGIES,
                    reason=str(exc),
                )
            ]

        results: list[IngestionResult] = []
        for record in commits:
            result = self.ingest_git_commit(record.sha, language)
            results.append(result)
        return results

    def ingest_code_fingerprint(
        self,
        code: str,
        language: str,
        context_id: str = "manual",
    ) -> IngestionResult:
        """
        Derive a style fingerprint from code and write it into Stream A.

        Formatting patterns and architectural preferences are embedded as
        document text. Metadata remains exactly the existing Stream A schema:
        ``language``, ``framework``, ``state_pattern``, ``naming_convention``.
        """
        try:
            fingerprint = self._extractor.extract(code, language)
            metadata = self._extractor.to_stream_a_metadata(fingerprint)
            text = self._extractor.to_stream_a_document(fingerprint)
            embedding = self._embedder.embed(text)
            doc_id = self._doc_id(f"fingerprint:{context_id}:{language}", text)
            self._controller.add_document(
                COLLECTION_CODE_TOPOLOGIES,
                doc_id=doc_id,
                text=text,
                metadata=metadata,
                embedding=embedding,
            )
            return IngestionResult(
                status="ok",
                collection=COLLECTION_CODE_TOPOLOGIES,
                doc_ids=[doc_id],
            )
        except (StyleExtractionError, ValueError) as exc:
            return IngestionResult(
                status="skipped",
                collection=COLLECTION_CODE_TOPOLOGIES,
                reason=str(exc),
            )
        except Exception as exc:
            logger.warning("ingest_code_fingerprint: failed - %s", exc)
            return IngestionResult(
                status="error",
                collection=COLLECTION_CODE_TOPOLOGIES,
                reason=str(exc),
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ingest_code_file(self, event: FileChangeEvent) -> IngestionResult:
        """Read a code file, chunk it via v0.1, fingerprint it, embed, and write Stream A."""
        language = _EXT_TO_LANGUAGE.get(event.extension, "python")

        try:
            code = Path(event.path).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning("_ingest_code_file: cannot read '%s': %s", event.path, exc)
            return IngestionResult(
                status="error",
                collection=COLLECTION_CODE_TOPOLOGIES,
                reason=f"Cannot read file: {exc}",
            )

        if not code.strip():
            return IngestionResult(
                status="skipped",
                collection=COLLECTION_CODE_TOPOLOGIES,
                reason=f"File is empty: {event.path}",
            )

        try:
            chunks = chunk_stream_a_code_topologies(code, language)
        except ValueError as exc:
            return IngestionResult(
                status="skipped",
                collection=COLLECTION_CODE_TOPOLOGIES,
                reason=f"Unsupported language '{language}': {exc}",
            )

        written_ids: list[str] = []
        for i, chunk in enumerate(chunks):
            if len(chunk) > 32000:
                logger.warning(
                    "_ingest_code_file: chunk %d for '%s' exceeds 32000 chars (approx 8192 tokens) and will be skipped.",
                    i, event.path
                )
                continue

            doc_id = self._doc_id(f"file:{event.path}:{i}", chunk)
            try:
                fp = self._extractor.extract(chunk, language)
                metadata = self._extractor.to_stream_a_metadata(fp)
                embedding = self._embedder.embed(chunk)
                self._controller.add_document(
                    COLLECTION_CODE_TOPOLOGIES,
                    doc_id=doc_id,
                    text=chunk,
                    metadata=metadata,
                    embedding=embedding,
                )
                written_ids.append(doc_id)
            except Exception as exc:
                logger.warning(
                    "_ingest_code_file: chunk %d failed for '%s': %s",
                    i, event.path, exc,
                )

        fingerprint_result = self.ingest_code_fingerprint(
            code,
            language,
            context_id=f"file:{event.path}",
        )
        if fingerprint_result.status == "ok":
            written_ids.extend(fingerprint_result.doc_ids)

        # Also log the file change as a Stream C telemetry event
        self._write_telemetry_event(
            text=f"file {event.event_type}: {event.path}",
            epoch_timestamp=event.epoch_timestamp,
            active_repository=event.repository,
            context_suffix=f"file:{Path(event.path).name}",
        )

        return IngestionResult(
            status="ok" if written_ids else "skipped",
            collection=COLLECTION_CODE_TOPOLOGIES,
            doc_ids=written_ids,
            reason="" if written_ids else f"No chunks produced from: {event.path}",
        )

    def _ingest_telemetry_event(self, event: FileChangeEvent) -> IngestionResult:
        """Log a non-code file change as a Stream C telemetry event."""
        text = f"file {event.event_type}: {event.path}"
        doc_id = self._write_telemetry_event(
            text=text,
            epoch_timestamp=event.epoch_timestamp,
            active_repository=event.repository,
            context_suffix=f"noncod:{Path(event.path).name}",
        )
        return IngestionResult(
            status="ok",
            collection=COLLECTION_AMBIENT_TELEMETRY,
            doc_ids=[doc_id] if doc_id else [],
        )

    def _write_telemetry_event(
        self,
        text: str,
        epoch_timestamp: int,
        active_repository: str,
        context_suffix: str,
    ) -> str:
        """
        Embed and write a single telemetry event into Stream C.

        Returns the doc_id on success, empty string on failure.
        """
        # active_repository must be a non-empty string; fall back to "houseconnect"
        # (the second valid value in the spec schema) when the repo cannot be inferred.
        repo = active_repository if active_repository else "houseconnect"
        # Clamp to valid Literal values expected by AmbientTelemetryMetadata
        valid_repos = {"smart_transit", "houseconnect"}
        if repo not in valid_repos:
            repo = "houseconnect"

        metadata: dict[str, Any] = {
            "epoch_timestamp": int(epoch_timestamp or time.time()),
            "active_repository": repo,
            "device_source": DEVICE_SOURCE,
        }
        doc_id = self._doc_id(context_suffix, text)
        try:
            embedding = self._embedder.embed(text)
            self._controller.add_document(
                COLLECTION_AMBIENT_TELEMETRY,
                doc_id=doc_id,
                text=text,
                metadata=metadata,
                embedding=embedding,
            )
            logger.debug("_write_telemetry_event: wrote '%s' to Stream C.", doc_id)
            return doc_id
        except Exception as exc:
            logger.warning("_write_telemetry_event: failed — %s", exc)
            return ""

    @staticmethod
    def _doc_id(prefix: str, content: str) -> str:
        """
        Generate a stable, unique document ID from a prefix and content hash.

        Uses the first 12 hex characters of a SHA-256 hash of the content so
        re-ingesting the same content produces the same ID (idempotent upserts).
        """
        content_hash = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()[:12]
        # Sanitise prefix to avoid ChromaDB ID restrictions
        safe_prefix = re.sub(r"[^a-zA-Z0-9_\-]", "_", prefix)[:40]
        return f"{safe_prefix}_{content_hash}"
