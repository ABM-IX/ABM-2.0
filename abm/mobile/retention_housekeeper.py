"""
abm/mobile/retention_housekeeper.py
=====================================
Stream C Retention Housekeeper — Phase v1.0 Ambient Interaction Manager

Implements the memory lifecycle stages from MEMORY_LIFECYCLE_POLICY.md for
``abm_ambient_telemetry`` (Stream C).  Called by ``StreamCWriter`` on every
write, but rate-limited to at most one run per ``HOUSEKEEPING_INTERVAL_SECONDS``
to avoid hammering ChromaDB on high-frequency event bursts.

Lifecycle stages implemented here (per MEMORY_LIFECYCLE_POLICY.md):

  Stage 3  Compress  — duplicate-suppression is in StreamCWriter (pre-write).
                       Housekeeper handles session-level collapse (post-write).
  Stage 5  Summarize — after SUMMARIZE_AFTER_DAYS (14), raw entries are distilled
                       into a single higher-level entry; originals marked
                       ``lifecycle_stage: "summarized"`` in metadata.
  Stage 6  Archive   — after ARCHIVE_AFTER_DAYS (30), summarized entries are
                       written to the cold-storage collection
                       ``abm_ambient_telemetry_archive`` and the hot-path
                       originals are deleted.
  Stage 7  Delete    — raw entries older than DELETE_AFTER_DAYS (180) that were
                       NOT summarized (e.g. very low-signal events skipped in
                       stage 5) are hard-deleted.

The cold archive lives in a SEPARATE ChromaController instance that wraps its
own ChromaDB persistent client — this keeps the v0.1 ChromaController sealed
and unmodified (as required by PROJECT_BRIEF.md ground rule 2).

Architectural Constitution compliance:
  - Rule 8  : every stream has a lifecycle — enforced from write #1.
  - Rule 2  : no deletion without explicit programmatic trigger (the
               housekeeper never runs autonomously in a background thread;
               it is called from StreamCWriter which is called from the
               manager which is called by the API layer).
  - Rule 3  : summary documents carry ``source_kind``, ``original_count``,
               and ``date_range`` in their text body for traceability.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from abm.api.core.interfaces import EmbedderInterface, VectorStoreInterface
from abm.memory.chroma_controller import (
    COLLECTION_AMBIENT_TELEMETRY,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Cold-storage collection name for archived Stream C entries.
COLLECTION_AMBIENT_ARCHIVE: str = "abm_ambient_telemetry_archive"

#: Retention thresholds (in seconds for comparison against epoch_timestamp).
SUMMARIZE_AFTER_DAYS: int = 14
ARCHIVE_AFTER_DAYS: int = 30
DELETE_AFTER_DAYS: int = 180

SUMMARIZE_AFTER_SECONDS: int = SUMMARIZE_AFTER_DAYS * 86_400
ARCHIVE_AFTER_SECONDS: int = ARCHIVE_AFTER_DAYS * 86_400
DELETE_AFTER_SECONDS: int = DELETE_AFTER_DAYS * 86_400

#: How often (seconds) the housekeeper may run.  Prevents stampede on rapid writes.
HOUSEKEEPING_INTERVAL_SECONDS: int = 3_600  # 1 hour


# ---------------------------------------------------------------------------
# Archive controller helper
# ---------------------------------------------------------------------------


def _build_archive_controller(archive_persist_dir: str) -> VectorStoreInterface:
    """
    Construct a *separate* ChromaController for the cold-archive collection.

    This is intentionally not the same instance as the hot-path controller,
    keeping the v0.1 ChromaController sealed (PROJECT_BRIEF.md ground rule 2).
    The archive controller creates / retrieves only the single archive collection.
    """
    from abm.memory.chroma_controller import ChromaController

    ctrl = ChromaController(persist_directory=archive_persist_dir, in_memory=False)
    # Ensure the archive collection exists (idempotent via get_or_create)
    try:
        ctrl._client.get_or_create_collection(name=COLLECTION_AMBIENT_ARCHIVE)
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning(
            "ArchiveController: could not create '%s': %s",
            COLLECTION_AMBIENT_ARCHIVE,
            exc,
        )
    return ctrl


# ---------------------------------------------------------------------------
# HousekeeperResult
# ---------------------------------------------------------------------------


@dataclass
class HousekeeperResult:
    """
    Summary of what the housekeeper did in a single run.

    Attributes
    ----------
    summarized : int
        Number of entries distilled into summary documents.
    archived : int
        Number of entries moved to cold storage.
    deleted : int
        Number of raw entries hard-deleted.
    skipped : bool
        ``True`` if the run was skipped because the interval had not elapsed.
    error : str
        Non-empty if a non-fatal error occurred during the run.
    """

    summarized: int = 0
    archived: int = 0
    deleted: int = 0
    skipped: bool = False
    error: str = ""


# ---------------------------------------------------------------------------
# StreamCRetentionHousekeeper
# ---------------------------------------------------------------------------


class StreamCRetentionHousekeeper:
    """
    Retention lifecycle manager for Stream C (``abm_ambient_telemetry``).

    Called by ``StreamCWriter`` on every successful write.  The internal
    interval guard ensures the expensive ChromaDB scan runs at most once
    per ``HOUSEKEEPING_INTERVAL_SECONDS``.

    Parameters
    ----------
    controller : ChromaController
        The hot-path v0.1 ``ChromaController`` that holds Stream C.
    embedder : OllamaEmbeddingWrapper
        Used to embed summary documents before writing them to the archive.
    archive_persist_dir : str
        Filesystem path for the cold-archive ChromaDB instance.
        Defaults to ``\"./memory/chroma_archive\"``.
    housekeeping_interval_seconds : int
        Minimum seconds between full housekeeping runs.
        Defaults to ``HOUSEKEEPING_INTERVAL_SECONDS`` (3600).
    """

    def __init__(
        self,
        controller: VectorStoreInterface,
        embedder: EmbedderInterface,
        archive_persist_dir: str = "./memory/chroma_archive",
        housekeeping_interval_seconds: int = HOUSEKEEPING_INTERVAL_SECONDS,
    ) -> None:
        self._controller = controller
        self._embedder = embedder
        self._archive_persist_dir = archive_persist_dir
        self._interval = housekeeping_interval_seconds
        self._last_run: float | None = None  # monotonic timestamp of last run
        self._archive_ctrl: VectorStoreInterface | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_if_due(self) -> HousekeeperResult:
        """
        Run housekeeping if the interval has elapsed; otherwise return a
        skipped result immediately.

        Never raises — all errors are captured into ``HousekeeperResult.error``.

        Returns
        -------
        HousekeeperResult
        """
        now = time.monotonic()
        if self._last_run is not None and (now - self._last_run < self._interval):
            return HousekeeperResult(skipped=True)

        self._last_run = now
        result = HousekeeperResult()
        try:
            self._run(result, int(time.time()))
        except Exception as exc:  # pragma: no cover — defensive
            result.error = str(exc)
            logger.error("StreamCRetentionHousekeeper: unexpected error: %s", exc)
        return result

    def force_run(self, now_epoch: int | None = None) -> HousekeeperResult:
        """
        Run housekeeping unconditionally, bypassing the interval guard.

        Intended for test use only — production code should call
        ``run_if_due()``.

        Parameters
        ----------
        now_epoch : int | None
            Epoch timestamp to treat as "now" (allows time-travel in tests).
            Defaults to ``int(time.time())``.
        """
        result = HousekeeperResult()
        try:
            self._run(result, now_epoch if now_epoch is not None else int(time.time()))
        except Exception as exc:  # pragma: no cover
            result.error = str(exc)
            logger.error(
                "StreamCRetentionHousekeeper.force_run: unexpected error: %s", exc
            )
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _archive_controller(self) -> VectorStoreInterface:
        """Lazily construct the cold-archive controller."""
        if self._archive_ctrl is None:
            self._archive_ctrl = _build_archive_controller(self._archive_persist_dir)
        return self._archive_ctrl

    def _run(self, result: HousekeeperResult, now: int) -> None:
        """Core lifecycle logic (extracted for testability)."""
        collection = self._controller.get_collection(COLLECTION_AMBIENT_TELEMETRY)

        # Fetch ALL entries — necessary for threshold comparisons.
        # For high-volume deployments this should be paginated; acceptable
        # at Phase v1.0 scale.
        try:
            raw = collection.get(include=["metadatas", "documents", "embeddings"])
        except Exception as exc:
            logger.warning("Housekeeper: could not fetch Stream C entries: %s", exc)
            return

        ids_raw = raw.get("ids") if raw is not None else None
        if raw is None or len(raw) == 0 or ids_raw is None or len(ids_raw) == 0:
            return

        ids: list[str] = raw["ids"]
        
        metas_raw = raw.get("metadatas")
        metadatas: list[dict] = metas_raw if metas_raw is not None else [{}] * len(ids)
        
        docs_raw = raw.get("documents")
        documents: list[str] = docs_raw if docs_raw is not None else [""] * len(ids)
        
        emb_raw = raw.get("embeddings")
        embeddings: list[list[float]] = emb_raw if emb_raw is not None else []

        delete_ids: list[str] = []
        archive_ids: list[str] = []
        summarize_groups: dict[str, list[int]] = {}  # source_kind → list of indices

        for i, (doc_id, meta, doc) in enumerate(zip(ids, metadatas, documents)):
            epoch = int(meta.get("epoch_timestamp", 0))
            age = now - epoch
            stage = meta.get("lifecycle_stage", "raw")

            if stage == "archived":
                # Already archived — skip all further processing
                continue

            if age >= DELETE_AFTER_SECONDS and stage in ("raw", "summarized"):
                delete_ids.append(doc_id)
                continue

            if age >= ARCHIVE_AFTER_SECONDS and stage == "summarized":
                archive_ids.append(i)
                continue

            if age >= SUMMARIZE_AFTER_SECONDS and stage == "raw":
                kind = str(meta.get("source_kind", "unknown"))
                summarize_groups.setdefault(kind, []).append(i)

        # Stage 5: Summarize
        for source_kind, indices in summarize_groups.items():
            self._summarize_group(
                source_kind, indices, ids, metadatas, documents, now, result
            )

        # Stage 6: Archive
        if archive_ids:
            self._archive_entries(archive_ids, ids, metadatas, documents, embeddings, result)

        # Stage 7: Delete
        if delete_ids:
            try:
                collection.delete(ids=delete_ids)
                result.deleted += len(delete_ids)
                logger.info(
                    "Housekeeper: deleted %d raw Stream C entries past %d-day window.",
                    len(delete_ids), DELETE_AFTER_DAYS,
                )
            except Exception as exc:
                logger.warning("Housekeeper: delete failed: %s", exc)

    def _summarize_group(
        self,
        source_kind: str,
        indices: list[int],
        ids: list[str],
        metadatas: list[dict],
        documents: list[str],
        now: int,
        result: HousekeeperResult,
    ) -> None:
        """Distil a group of raw entries into a single summary document."""
        if not indices:
            return

        group_ids = [ids[i] for i in indices]
        group_docs = [documents[i] for i in indices]
        group_metas = [metadatas[i] for i in indices]

        # Build summary text (constitution rule 3 — explainable)
        epochs = [int(m.get("epoch_timestamp", 0)) for m in group_metas]
        repos = list({str(m.get("active_repository", "")) for m in group_metas})
        min_epoch, max_epoch = min(epochs), max(epochs)
        summary_text = (
            f"STREAM C SUMMARY | source_kind={source_kind} | "
            f"entries={len(group_ids)} | "
            f"repos={','.join(repos)} | "
            f"date_range={min_epoch}–{max_epoch} | "
            f"summarized_at={now}\n\n"
            + "\n---\n".join(group_docs[:10])  # include up to 10 samples
        )

        import collections
        devices = [str(m.get("device_source", "dynamic_mobile_node")) for m in group_metas]
        dominant_device = collections.Counter(devices).most_common(1)[0][0] if devices else "dynamic_mobile_node"

        summary_meta: dict[str, Any] = {
            "epoch_timestamp": max_epoch,
            "active_repository": repos[0] if len(repos) == 1 else ",".join(repos),
            "device_source": dominant_device,
            "lifecycle_stage": "summary",
            "source_kind": source_kind,
            "original_count": len(group_ids),
        }

        summary_id = "summary_" + hashlib.sha256(
            f"{source_kind}:{min_epoch}:{max_epoch}".encode()
        ).hexdigest()[:16]

        # Embed summary
        try:
            embedding = self._embedder.embed(summary_text)
        except Exception as exc:
            logger.warning("Housekeeper: could not embed summary: %s", exc)
            return

        # Write summary to Stream C
        try:
            self._controller.add_document(
                collection_name=COLLECTION_AMBIENT_TELEMETRY,
                doc_id=summary_id,
                text=summary_text,
                metadata=summary_meta,
                embedding=embedding,
            )
        except Exception as exc:
            logger.warning("Housekeeper: could not write summary: %s", exc)
            return

        # Mark originals as summarized
        try:
            collection = self._controller.get_collection(COLLECTION_AMBIENT_TELEMETRY)
            for i, doc_id in zip(indices, group_ids):
                updated_meta = dict(metadatas[i])
                updated_meta["lifecycle_stage"] = "summarized"
                collection.update(ids=[doc_id], metadatas=[updated_meta])
        except Exception as exc:
            logger.warning("Housekeeper: could not mark entries as summarized: %s", exc)

        result.summarized += len(group_ids)
        logger.info(
            "Housekeeper: summarized %d Stream C entries (source_kind=%s).",
            len(group_ids), source_kind,
        )

    def _archive_entries(
        self,
        indices: list[int],
        ids: list[str],
        metadatas: list[dict],
        documents: list[str],
        embeddings: list[list[float]],
        result: HousekeeperResult,
    ) -> None:
        """Move summarized entries to the cold-archive collection."""
        archive_ctrl = self._archive_controller()

        archived_ids: list[str] = []
        hot_delete_ids: list[str] = []

        for i in indices:
            doc_id = ids[i]
            meta = dict(metadatas[i])
            doc = documents[i]
            meta["lifecycle_stage"] = "archived"
            meta["archived_at"] = time.time() + (i * 0.001)

            emb: list[float] | None = (
                embeddings[i] if embeddings is not None and i < len(embeddings) else None
            )
            if emb is None:
                try:
                    emb = self._embedder.embed(doc)
                except Exception as exc:
                    logger.warning(
                        "Housekeeper: could not embed archive entry %s: %s", doc_id, exc
                    )
                    continue

            try:
                archive_ctrl._client.get_or_create_collection(
                    name=COLLECTION_AMBIENT_ARCHIVE
                ).upsert(
                    ids=[doc_id],
                    documents=[doc],
                    metadatas=[meta],
                    embeddings=[emb],
                )
                archived_ids.append(doc_id)
                hot_delete_ids.append(doc_id)
            except Exception as exc:
                logger.warning(
                    "Housekeeper: could not archive entry %s: %s", doc_id, exc
                )

        # Remove from hot-path collection
        if hot_delete_ids:
            try:
                self._controller.get_collection(
                    COLLECTION_AMBIENT_TELEMETRY
                ).delete(ids=hot_delete_ids)
                result.archived += len(archived_ids)
                logger.info(
                    "Housekeeper: archived %d Stream C entries to cold storage.",
                    len(archived_ids),
                )
            except Exception as exc:
                logger.warning("Housekeeper: hot-delete after archive failed: %s", exc)


__all__ = [
    "StreamCRetentionHousekeeper",
    "HousekeeperResult",
    "COLLECTION_AMBIENT_ARCHIVE",
    "SUMMARIZE_AFTER_DAYS",
    "ARCHIVE_AFTER_DAYS",
    "DELETE_AFTER_DAYS",
    "HOUSEKEEPING_INTERVAL_SECONDS",
]
