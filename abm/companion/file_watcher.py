"""
abm/companion/file_watcher.py
==============================
Workspace File Watcher — Phase v0.2 Developer Companion Node
Spec Reference: ABM_SPEC.md sections 2 and 3

Uses watchdog (cross-platform wrapper over ReadDirectoryChangesW on Windows
and inotify on Linux) to monitor workspace paths for file changes.

Design contract:
  - This module produces FileChangeEvent objects and delivers them via
    caller-supplied callbacks. It does NOT write to ChromaDB directly.
    All ingestion is delegated to IngestionCoordinator.
  - Code file extensions → on_code_change callback (→ Stream A)
  - All other extensions → on_telemetry_event callback (→ Stream C)
  - A debounce window collapses rapid save storms into one event per file.
  - The watcher runs in a background daemon thread — it never blocks the
    calling thread.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Extensions whose change events are forwarded as code events (→ Stream A).
CODE_EXTENSIONS: frozenset[str] = frozenset(
    {".py", ".dart", ".kt", ".java", ".js", ".css", ".html"}
)

#: device_source value per spec hardware-agnostic blueprint update (section 10 addendum).
DEVICE_SOURCE: str = "dynamic_mobile_node"

#: Default debounce window in seconds.
DEFAULT_DEBOUNCE_SECONDS: float = 1.0


# ---------------------------------------------------------------------------
# FileChangeEvent dataclass
# ---------------------------------------------------------------------------


@dataclass
class FileChangeEvent:
    """
    A normalised file system change event produced by WorkspaceFileWatcher.

    All fields are populated before the event is delivered to a callback,
    so callers never have to inspect raw watchdog events.

    Attributes
    ----------
    path : str
        Absolute path to the changed file.
    event_type : str
        One of ``"created"``, ``"modified"``, ``"deleted"``.
    epoch_timestamp : int
        Unix timestamp (integer seconds) at which the event was detected.
    repository : str
        Name of the Git repository inferred by walking up from ``path``
        until a ``.git`` directory is found. Empty string if none found.
    device_source : str
        Always ``"dynamic_mobile_node"`` per spec section 10 addendum.
    extension : str
        Lowercase file extension including the leading dot (e.g. ``".py"``).
        Empty string for files with no extension.
    is_code_file : bool
        ``True`` if ``extension`` is in ``CODE_EXTENSIONS``.
    """

    path: str
    event_type: str
    epoch_timestamp: int
    repository: str
    device_source: str = DEVICE_SOURCE
    extension: str = field(init=False)
    is_code_file: bool = field(init=False)

    def __post_init__(self) -> None:
        self.extension = Path(self.path).suffix.lower()
        self.is_code_file = self.extension in CODE_EXTENSIONS


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _infer_repository(file_path: str) -> str:
    """
    Walk up the directory tree from ``file_path`` to find a ``.git`` directory.

    Returns the basename of the directory that contains ``.git``, or an empty
    string if no Git repository is found.
    """
    current = Path(file_path).resolve().parent
    for parent in [current, *current.parents]:
        if (parent / ".git").exists():
            return parent.name
    return ""


# ---------------------------------------------------------------------------
# Internal watchdog event handler
# ---------------------------------------------------------------------------


class _DebounceHandler(FileSystemEventHandler):
    """
    Watchdog event handler with per-file debounce logic.

    When a file changes multiple times within ``debounce_seconds``, only the
    last event in the window is forwarded to the callbacks.
    """

    def __init__(
        self,
        on_code_change: Callable[[FileChangeEvent], None],
        on_telemetry_event: Callable[[FileChangeEvent], None],
        debounce_seconds: float,
    ) -> None:
        super().__init__()
        self._on_code_change = on_code_change
        self._on_telemetry_event = on_telemetry_event
        self._debounce_seconds = debounce_seconds
        self._pending: dict[str, tuple[str, float]] = {}  # path → (event_type, fire_at)
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None

    # ------------------------------------------------------------------
    # watchdog overrides
    # ------------------------------------------------------------------

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._schedule(str(event.src_path), "created")

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._schedule(str(event.src_path), "modified")

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._schedule(str(event.src_path), "deleted")

    # ------------------------------------------------------------------
    # Debounce logic
    # ------------------------------------------------------------------

    def _schedule(self, path: str, event_type: str) -> None:
        """Queue an event for ``path`` and reset its debounce timer."""
        fire_at = time.monotonic() + self._debounce_seconds
        with self._lock:
            self._pending[path] = (event_type, fire_at)
        self._arm_timer()

    def _arm_timer(self) -> None:
        """Cancel any running timer and start a fresh one."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._debounce_seconds, self._flush)
            self._timer.daemon = True
            self._timer.start()

    def _flush(self) -> None:
        """Fire all pending events whose debounce window has elapsed."""
        now = time.monotonic()
        to_fire: list[tuple[str, str]] = []
        with self._lock:
            remaining: dict[str, tuple[str, float]] = {}
            for path, (event_type, fire_at) in self._pending.items():
                if now >= fire_at:
                    to_fire.append((path, event_type))
                else:
                    remaining[path] = (event_type, fire_at)
            self._pending = remaining
            if remaining:
                self._arm_timer()

        for path, event_type in to_fire:
            self._dispatch(path, event_type)

    def _dispatch(self, path: str, event_type: str) -> None:
        """Build a FileChangeEvent and route it to the correct callback."""
        evt = FileChangeEvent(
            path=path,
            event_type=event_type,
            epoch_timestamp=int(time.time()),
            repository=_infer_repository(path),
        )
        logger.debug(
            "FileWatcher dispatch: %s %s (repo=%s, code=%s)",
            event_type, path, evt.repository, evt.is_code_file,
        )
        if evt.is_code_file:
            self._on_code_change(evt)
        else:
            self._on_telemetry_event(evt)


# ---------------------------------------------------------------------------
# WorkspaceFileWatcher
# ---------------------------------------------------------------------------


class WorkspaceFileWatcher:
    """
    Monitors one or more workspace directory paths for file changes.

    Runs a watchdog Observer in a background daemon thread. All detected
    file-system events are normalised into ``FileChangeEvent`` objects and
    delivered via caller-supplied callbacks — this class never touches
    ChromaDB directly.

    Parameters
    ----------
    watch_paths : list[str]
        Absolute directory paths to monitor recursively.
    on_code_change : Callable[[FileChangeEvent], None]
        Called when a code file (see ``CODE_EXTENSIONS``) changes.
        Intended to feed into Stream A ingestion.
    on_telemetry_event : Callable[[FileChangeEvent], None]
        Called when a non-code file changes.
        Intended to feed into Stream C ingestion.
    debounce_seconds : float
        Time window (seconds) to collapse rapid save storms into a single
        event per file. Defaults to ``1.0``.
    """

    def __init__(
        self,
        watch_paths: list[str],
        on_code_change: Callable[[FileChangeEvent], None],
        on_telemetry_event: Callable[[FileChangeEvent], None],
        debounce_seconds: float = DEFAULT_DEBOUNCE_SECONDS,
    ) -> None:
        if not watch_paths:
            raise ValueError("WorkspaceFileWatcher: watch_paths must not be empty.")

        self._watch_paths = [str(p) for p in watch_paths]
        self._on_code_change = on_code_change
        self._on_telemetry_event = on_telemetry_event
        self._debounce_seconds = debounce_seconds

        self._handler = _DebounceHandler(
            on_code_change=on_code_change,
            on_telemetry_event=on_telemetry_event,
            debounce_seconds=debounce_seconds,
        )
        self._observer: Observer = Observer()
        self._running = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """
        Start the file-system observer in a background daemon thread.

        Idempotent — calling ``start()`` on an already-running watcher is
        a no-op.

        Raises
        ------
        FileNotFoundError
            If any path in ``watch_paths`` does not exist.
        """
        if self._running:
            logger.debug("WorkspaceFileWatcher.start: already running.")
            return

        for path in self._watch_paths:
            if not os.path.isdir(path):
                raise FileNotFoundError(
                    f"WorkspaceFileWatcher: watch path does not exist: '{path}'"
                )
            self._observer.schedule(self._handler, path, recursive=True)
            logger.info("WorkspaceFileWatcher: watching '%s' recursively.", path)

        self._observer.start()
        self._running = True
        logger.info("WorkspaceFileWatcher: observer started.")

    def stop(self) -> None:
        """
        Stop the file-system observer and block until its thread joins.

        Idempotent — safe to call if the watcher is not running.
        """
        if not self._running:
            return
        self._observer.stop()
        self._observer.join()
        self._running = False
        logger.info("WorkspaceFileWatcher: observer stopped.")

    def is_running(self) -> bool:
        """
        Return ``True`` if the background observer thread is active.

        Returns
        -------
        bool
        """
        return self._running

    @property
    def watch_paths(self) -> list[str]:
        """The directory paths being monitored."""
        return list(self._watch_paths)

    @property
    def debounce_seconds(self) -> float:
        """The debounce window in seconds."""
        return self._debounce_seconds
