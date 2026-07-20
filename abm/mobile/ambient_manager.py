"""
abm/mobile/ambient_manager.py
==============================
Ambient Interaction Manager — Phase v1.0

Top-level orchestrator for all Phase v1.0 permitted telemetry sources.
Wires three data-source monitors to a single ``StreamCWriter`` instance.

Permitted sources (Phase v1.0 scope — PROJECT_BRIEF.md ground rule 8):
  - ``GitTreeMonitor``        — wraps existing ``GitPipeline`` (v0.2).
  - ``WorkspaceStateMonitor`` — wraps existing ``WorkspaceFileWatcher`` (v0.2),
                                filtered to design-doc extensions only
                                (.md, .txt, .rst, .yaml, .yml, .json).
  - ``DesignDocMonitor``      — one-shot scan of specified design-doc directories
                                on startup.

Explicitly OFFLINE for this phase (clipboard, voice, browser):
  Any attempt to pass a source_kind outside PERMITTED_SOURCE_KINDS will be
  rejected by ``AmbientEvent.__post_init__()`` and ``StreamCWriter.write()``.

Architectural Constitution compliance:
  - Rule 9  : degraded gracefully when Ollama / Git is unavailable.
  - Rule 12 : this module is backend only — no CLI / Flutter UI binds here.
  - Rule 13 : callers (API layer) access this via ``ingestAmbientEvent``
               capability; they never import this module directly.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from abm.companion.file_watcher import (
    FileChangeEvent,
    WorkspaceFileWatcher,
    _is_excluded,
)
from abm.companion.git_pipeline import GitPipeline, GitPipelineError
from abm.memory.chroma_controller import ChromaController
from abm.memory.embedding_wrapper import OllamaEmbeddingWrapper

from .event_models import AmbientEvent
from .retention_housekeeper import StreamCRetentionHousekeeper
from .stream_c_writer import StreamCWriter, WriteResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Design-doc extensions allowed by WorkspaceStateMonitor
# ---------------------------------------------------------------------------

#: File extensions considered "design documents" for workspace-state telemetry.
#: Code files are already ingested by v0.2 IngestionCoordinator → Stream A.
#: Only non-code design / spec files feed Stream C here.
DESIGN_DOC_EXTENSIONS: frozenset[str] = frozenset(
    {".md", ".txt", ".rst", ".yaml", ".yml", ".json", ".toml"}
)


# ---------------------------------------------------------------------------
# GitTreeMonitor
# ---------------------------------------------------------------------------


class GitTreeMonitor:
    """
    Watches a Git repository for new commits and emits ``AmbientEvent`` objects.

    This is a *polling* monitor, not event-driven — it checks for commits newer
    than its last-seen SHA on each ``poll()`` call.  The caller (daemon loop /
    Flutter foreground service) decides how often to poll.

    Parameters
    ----------
    git_pipeline : GitPipeline
        The v0.2 ``GitPipeline`` connected to the repository to monitor.
    on_event : Callable[[AmbientEvent], None]
        Callback invoked for each new commit detected.
    """

    def __init__(
        self,
        git_pipeline: GitPipeline,
        on_event: Callable[[AmbientEvent], None],
    ) -> None:
        self._pipeline = git_pipeline

        self._on_event = on_event
        self._last_sha: str | None = None

    def poll(self) -> int:
        """
        Check for new commits and emit events for each new one.

        Returns the number of new commits emitted.  Never raises.
        """
        try:
            commits = self._pipeline.list_commits(max_count=20)
        except GitPipelineError as exc:
            logger.warning("GitTreeMonitor: poll failed: %s", exc)
            return 0

        if not commits:
            return 0

        head_sha = commits[0].sha

        # No last SHA yet — initialise without emitting (avoid replaying history)
        if self._last_sha is None:
            self._last_sha = head_sha
            return 0

        if head_sha == self._last_sha:
            return 0

        # Emit events for commits newer than last_sha
        emitted = 0
        for commit in commits:
            if commit.sha == self._last_sha:
                break
            try:
                evt = AmbientEvent(
                    source_kind="git_commit",
                    active_repository=self._pipeline.repo_name(),
                    source_path=commit.sha,
                    text=(
                        f"git commit {commit.sha[:8]}: {commit.message}\n"
                        f"author={commit.author} files={len(commit.files_changed)}"
                    ),
                    epoch_timestamp=commit.epoch_timestamp,
                    extra={"sha": commit.sha, "author": commit.author},
                )
                self._on_event(evt)
                emitted += 1
            except Exception as exc:
                logger.warning(
                    "GitTreeMonitor: could not emit event for %s: %s",
                    commit.sha[:8], exc,
                )

        self._last_sha = head_sha
        return emitted


# ---------------------------------------------------------------------------
# WorkspaceStateMonitor
# ---------------------------------------------------------------------------


class WorkspaceStateMonitor:
    """
    Wraps ``WorkspaceFileWatcher`` and filters events to design-doc paths only.

    Code files are handled by v0.2 ``IngestionCoordinator`` → Stream A.
    This monitor forwards only non-code, non-excluded design-document changes
    to Stream C via ``AmbientEvent(source_kind="workspace_file", ...)``.

    Parameters
    ----------
    watch_paths : list[str]
        Absolute directory paths to monitor (passed through to watchdog).
    on_event : Callable[[AmbientEvent], None]
        Callback for each qualifying file-change event.
    debounce_seconds : float
        Debounce window forwarded to ``WorkspaceFileWatcher``.
    """

    def __init__(
        self,
        watch_paths: list[str],
        on_event: Callable[[AmbientEvent], None],
        debounce_seconds: float = 1.0,
    ) -> None:
        self._on_event = on_event
        self._watcher: WorkspaceFileWatcher | None = None

        if not watch_paths:
            logger.warning("WorkspaceStateMonitor: no watch_paths provided; inactive.")
            return

        self._watcher = WorkspaceFileWatcher(
            watch_paths=watch_paths,
            on_code_change=self._on_code_change,
            on_telemetry_event=self._on_telemetry_event,
            debounce_seconds=debounce_seconds,
        )

    def start(self) -> None:
        """Start the underlying file-system observer. Idempotent."""
        if self._watcher:
            self._watcher.start()

    def stop(self) -> None:
        """Stop the underlying file-system observer. Idempotent."""
        if self._watcher:
            self._watcher.stop()

    # ------------------------------------------------------------------
    # Watcher callbacks
    # ------------------------------------------------------------------

    def _on_code_change(self, fce: FileChangeEvent) -> None:
        # Code changes → Stream A (handled by IngestionCoordinator, not here)
        logger.debug(
            "WorkspaceStateMonitor: code change ignored (Stream A handles it): %s",
            fce.path,
        )

    def _on_telemetry_event(self, fce: FileChangeEvent) -> None:
        """Forward qualifying design-doc changes as AmbientEvents."""
        ext = Path(fce.path).suffix.lower()
        if ext not in DESIGN_DOC_EXTENSIONS:
            logger.debug(
                "WorkspaceStateMonitor: skipping non-design-doc extension %s: %s",
                ext, fce.path,
            )
            return

        if _is_excluded(fce.path):
            # Should already be excluded by WorkspaceFileWatcher, but double-guard
            return

        try:
            evt = AmbientEvent(
                source_kind="workspace_file",
                active_repository=fce.repository,
                source_path=fce.path,
                text=(
                    f"workspace file {fce.event_type}: {fce.path}\n"
                    f"extension={ext} repo={fce.repository}"
                ),
                epoch_timestamp=fce.epoch_timestamp,
            )
            self._on_event(evt)
        except Exception as exc:
            logger.warning(
                "WorkspaceStateMonitor: could not emit event for %s: %s",
                fce.path, exc,
            )


# ---------------------------------------------------------------------------
# DesignDocMonitor
# ---------------------------------------------------------------------------


class DesignDocMonitor:
    """
    One-shot scanner that discovers design documents on disk at startup.

    Emits one ``AmbientEvent(source_kind="design_doc", ...)`` per discovered
    file.  This provides an initial snapshot of the static design corpus so
    that the memory core is aware of the project's specification documents
    from the first run.

    Parameters
    ----------
    scan_paths : list[str]
        Absolute directory paths to scan recursively.
    on_event : Callable[[AmbientEvent], None]
        Callback for each discovered document.
    extensions : frozenset[str] | None
        File extensions to include.  Defaults to ``DESIGN_DOC_EXTENSIONS``.
    """

    def __init__(
        self,
        scan_paths: list[str],
        on_event: Callable[[AmbientEvent], None],
        extensions: frozenset[str] | None = None,
    ) -> None:
        self._scan_paths = scan_paths
        self._on_event = on_event
        self._extensions = extensions or DESIGN_DOC_EXTENSIONS

    def scan(self) -> int:
        """
        Perform the one-shot scan.  Returns the number of events emitted.
        Never raises.
        """
        emitted = 0
        for root_str in self._scan_paths:
            root = Path(root_str)
            if not root.is_dir():
                logger.warning(
                    "DesignDocMonitor: scan path does not exist: %s", root_str
                )
                continue

            for filepath in root.rglob("*"):
                if not filepath.is_file():
                    continue
                if filepath.suffix.lower() not in self._extensions:
                    continue
                if _is_excluded(str(filepath)):
                    continue

                try:
                    # Read a preview (first 2000 chars) for embedding quality
                    preview = filepath.read_text(encoding="utf-8", errors="replace")[
                        :2000
                    ]
                    mtime = int(filepath.stat().st_mtime)
                    # Infer repo from nearest .git
                    repo = _infer_repo(filepath)

                    evt = AmbientEvent(
                        source_kind="design_doc",
                        active_repository=repo,
                        source_path=str(filepath),
                        text=(
                            f"design doc: {filepath.name} | path: {filepath}\n\n"
                            f"{preview}"
                        ),
                        epoch_timestamp=mtime,
                    )
                    self._on_event(evt)
                    emitted += 1
                except Exception as exc:
                    logger.warning(
                        "DesignDocMonitor: could not emit event for %s: %s",
                        filepath, exc,
                    )

        logger.info("DesignDocMonitor: scan complete — emitted %d events.", emitted)
        return emitted


def _infer_repo(path: Path) -> str:
    """Walk up from ``path`` to find the nearest .git directory."""
    for parent in [path.parent, *path.parent.parents]:
        if (parent / ".git").exists():
            return parent.name
    return ""


# ---------------------------------------------------------------------------
# AmbientInteractionManager
# ---------------------------------------------------------------------------


@dataclass
class ManagerConfig:
    """
    Configuration for ``AmbientInteractionManager``.

    Attributes
    ----------
    watch_paths : list[str]
        Directories to watch with ``WorkspaceStateMonitor``.
    design_doc_paths : list[str]
        Directories to scan with ``DesignDocMonitor`` at startup.
    git_repo_path : str | None
        Path to a Git repository for ``GitTreeMonitor``.
        ``None`` disables Git monitoring.
    archive_persist_dir : str
        Filesystem path for the cold-archive ChromaDB instance.
    debounce_seconds : float
        Debounce window for ``WorkspaceStateMonitor``.
    git_poll_interval_seconds : int
        How often (seconds) the manager polls for new Git commits.
    """

    watch_paths: list[str] = field(default_factory=list)
    design_doc_paths: list[str] = field(default_factory=list)
    git_repo_path: str | None = None
    archive_persist_dir: str = "./memory/chroma_archive"
    debounce_seconds: float = 1.0
    git_poll_interval_seconds: int = 60


class AmbientInteractionManager:
    """
    Top-level ambient telemetry orchestrator for Phase v1.0.

    Wires ``GitTreeMonitor``, ``WorkspaceStateMonitor``, and
    ``DesignDocMonitor`` to a single retention-aware ``StreamCWriter``.

    Parameters
    ----------
    controller : ChromaController
        The hot-path v0.1 ``ChromaController``.
    embedder : OllamaEmbeddingWrapper
        Used by ``StreamCWriter`` and ``StreamCRetentionHousekeeper``.
    config : ManagerConfig
        Source and timing configuration.
    """

    def __init__(
        self,
        controller: ChromaController,
        embedder: OllamaEmbeddingWrapper,
        config: ManagerConfig | None = None,
    ) -> None:
        self._controller = controller
        self._embedder = embedder
        self._config = config or ManagerConfig()

        # Build the shared write path
        housekeeper = StreamCRetentionHousekeeper(
            controller=controller,
            embedder=embedder,
            archive_persist_dir=self._config.archive_persist_dir,
        )
        self._writer = StreamCWriter(
            controller=controller,
            embedder=embedder,
            housekeeper=housekeeper,
        )

        # Build monitors
        self._git_monitor: GitTreeMonitor | None = self._build_git_monitor()
        self._workspace_monitor = WorkspaceStateMonitor(
            watch_paths=self._config.watch_paths,
            on_event=self._handle_event,
            debounce_seconds=self._config.debounce_seconds,
        )
        self._design_doc_monitor = DesignDocMonitor(
            scan_paths=self._config.design_doc_paths,
            on_event=self._handle_event,
        )

        self._running = False
        self._last_git_poll: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """
        Start all background monitors and run the initial design-doc scan.

        Idempotent — calling when already running is a no-op.
        """
        if self._running:
            logger.debug("AmbientInteractionManager: already running.")
            return

        # One-shot design-doc scan at startup
        self._design_doc_monitor.scan()

        # Start workspace watcher (daemon thread)
        self._workspace_monitor.start()

        self._running = True
        logger.info("AmbientInteractionManager: started.")

    def stop(self) -> None:
        """Stop all background monitors. Idempotent."""
        if not self._running:
            return
        self._workspace_monitor.stop()
        self._running = False
        logger.info("AmbientInteractionManager: stopped.")

    def poll_git(self) -> int:
        """
        Poll for new Git commits if the poll interval has elapsed.

        Returns the number of new commit events emitted.
        Intended to be called from a timer / foreground-service tick.
        """
        if self._git_monitor is None:
            return 0
        now = time.monotonic()
        if now - self._last_git_poll < self._config.git_poll_interval_seconds:
            return 0
        self._last_git_poll = now
        return self._git_monitor.poll()

    def ingest_event(self, event: AmbientEvent) -> WriteResult:
        """
        Directly ingest a pre-built ``AmbientEvent``.

        Used by the API capability ``ingestAmbientEvent`` and by the Flutter
        foreground service when it constructs events locally.

        Returns the ``WriteResult`` from ``StreamCWriter``.
        """
        return self._writer.write(event)

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _handle_event(self, event: AmbientEvent) -> None:
        """Route an AmbientEvent from any monitor to the StreamCWriter."""
        result = self._writer.write(event)
        if result.status == "ok":
            logger.debug(
                "AmbientInteractionManager: wrote event %s (source_kind=%s)",
                result.doc_id, event.source_kind,
            )
        elif result.status == "compressed":
            logger.debug(
                "AmbientInteractionManager: compressed duplicate event "
                "(source_kind=%s, repo=%s)",
                event.source_kind, event.active_repository,
            )
        else:
            logger.warning(
                "AmbientInteractionManager: write %s — %s",
                result.status, result.reason,
            )

    def _build_git_monitor(self) -> GitTreeMonitor | None:
        if not self._config.git_repo_path:
            return None
        try:
            pipeline = GitPipeline(self._config.git_repo_path)
            return GitTreeMonitor(git_pipeline=pipeline, on_event=self._handle_event)

        except GitPipelineError as exc:
            logger.warning(
                "AmbientInteractionManager: Git monitor disabled (%s).", exc
            )
            return None


__all__ = [
    "AmbientInteractionManager",
    "ManagerConfig",
    "GitTreeMonitor",
    "WorkspaceStateMonitor",
    "DesignDocMonitor",
    "DESIGN_DOC_EXTENSIONS",
]
