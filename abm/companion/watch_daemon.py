"""
abm/companion/watch_daemon.py
==============================
Watch Daemon — Phase v0.2 Developer Companion Node
Spec Reference: ABM_SPEC.md sections 2, 3, and 10

Entry point that wires WorkspaceFileWatcher directly to IngestionCoordinator.
Every file-system event detected by the watcher is routed to the coordinator,
which writes it to the correct ChromaDB stream (Stream A for code, Stream C
for non-code), exactly as the v0.2 design specifies.

Usage
-----
    python -m abm.companion.watch_daemon --path <directory> [options]

Options
-------
    --path PATH             Directory to watch (required; repeat for multiple)
    --debounce SECONDS      Debounce window in seconds (default: 1.0)
    --chroma-dir DIR        ChromaDB persist directory (default: ./memory/chroma_store)
    --ollama-url URL        Ollama base URL (default: http://127.0.0.1:11434)
    --git-path DIR          Git repository path for GitPipeline (optional)
    --log-level LEVEL       Logging level: DEBUG|INFO|WARNING|ERROR (default: INFO)

Design contract
---------------
- WorkspaceFileWatcher.on_code_change  -> coordinator.ingest_file_change(event)
  -> Stream A (abm_code_topologies)
- WorkspaceFileWatcher.on_telemetry_event -> coordinator.ingest_file_change(event)
  -> Stream C (abm_ambient_telemetry)
- IngestionCoordinator is the ONLY object that writes to ChromaDB (v0.2 rule).
- A plain confirmation line is printed to stdout per ingested file so the
  pipeline is visually verifiable without log-level noise.
- The daemon runs until SIGINT (Ctrl-C) or SIGTERM.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from pathlib import Path
from typing import NoReturn

from abm.companion.file_watcher import FileChangeEvent, WorkspaceFileWatcher
from abm.companion.git_pipeline import GitPipeline, GitPipelineError
from abm.companion.ingestion_coordinator import IngestionCoordinator, IngestionResult
from abm.memory.chroma_controller import ChromaController
from abm.memory.embedding_wrapper import OllamaEmbeddingWrapper

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Confirmation output helpers
# ---------------------------------------------------------------------------

_STREAM_LABELS: dict[str, str] = {
    "abm_code_topologies": "Stream A [code]",
    "abm_ambient_telemetry": "Stream C [telemetry]",
    "abm_technical_mastery": "Stream B [docs]",
    "abm_cognitive_identity": "Stream D [identity]",
}


def _confirm(event: FileChangeEvent, result: IngestionResult) -> None:
    """
    Print a single confirmation line to stdout so the daemon's activity is
    immediately visible without needing to enable DEBUG logging.

    Format::

        [ok]      Stream A [code]      modified  abm/companion/file_watcher.py  (3 chunk(s))
        [skipped] Stream C [telemetry] deleted   some/file.txt  -- Deleted file -- nothing to embed
        [error]   Stream A [code]      created   broken.py  -- Cannot read file: ...
    """
    stream_label = _STREAM_LABELS.get(result.collection, result.collection)
    rel_path = _rel_path(event.path)
    status_tag = f"[{result.status:<7}]"

    if result.status == "ok":
        chunk_info = f"({len(result.doc_ids)} chunk(s))" if result.doc_ids else ""
        print(
            f"{status_tag} {stream_label:<22} {event.event_type:<10} {rel_path}  {chunk_info}",
            flush=True,
        )
    elif result.status == "skipped":
        reason = f" -- {result.reason}" if result.reason else ""
        print(
            f"{status_tag} {stream_label:<22} {event.event_type:<10} {rel_path}{reason}",
            flush=True,
        )
    else:  # error
        reason = f" -- {result.reason}" if result.reason else ""
        print(
            f"{status_tag} {stream_label:<22} {event.event_type:<10} {rel_path}{reason}",
            flush=True,
            file=sys.stderr,
        )


def _rel_path(absolute: str) -> str:
    """Return path relative to cwd where possible, for readable output."""
    try:
        return str(Path(absolute).relative_to(Path.cwd()))
    except ValueError:
        return absolute


# ---------------------------------------------------------------------------
# Callback factories
# ---------------------------------------------------------------------------


def _make_on_code_change(coordinator: IngestionCoordinator):
    """
    Return an ``on_code_change`` callback whose signature matches exactly::

        Callable[[FileChangeEvent], None]

    Routes the event to ``coordinator.ingest_file_change()`` -> Stream A.
    """

    def on_code_change(event: FileChangeEvent) -> None:
        logger.debug(
            "on_code_change: %s %s (ext=%s, repo=%s)",
            event.event_type, event.path, event.extension, event.repository,
        )
        result: IngestionResult = coordinator.ingest_file_change(event)
        _confirm(event, result)

    return on_code_change


def _make_on_telemetry_event(coordinator: IngestionCoordinator):
    """
    Return an ``on_telemetry_event`` callback whose signature matches exactly::

        Callable[[FileChangeEvent], None]

    Routes the event to ``coordinator.ingest_file_change()`` -> Stream C.
    """

    def on_telemetry_event(event: FileChangeEvent) -> None:
        logger.debug(
            "on_telemetry_event: %s %s (ext=%s, repo=%s)",
            event.event_type, event.path, event.extension, event.repository,
        )
        result: IngestionResult = coordinator.ingest_file_change(event)
        _confirm(event, result)

    return on_telemetry_event


# ---------------------------------------------------------------------------
# Daemon entry point
# ---------------------------------------------------------------------------


def build_coordinator(
    chroma_dir: str,
    ollama_url: str,
    git_path: str | None,
) -> IngestionCoordinator:
    """
    Construct the v0.1 + v0.2 object graph:
    ChromaController -> OllamaEmbeddingWrapper -> (optional) GitPipeline
    -> IngestionCoordinator.

    Parameters
    ----------
    chroma_dir:
        ChromaDB persistence directory (passed to ChromaController).
    ollama_url:
        Ollama base URL (passed to OllamaEmbeddingWrapper).
    git_path:
        Optional path to a local Git repository. If provided, a GitPipeline
        is attached to the coordinator; if absent or invalid, the coordinator
        runs without Git support (file-change ingestion is unaffected).

    Returns
    -------
    IngestionCoordinator
        Fully wired, ready to call ``ingest_file_change()``.
    """
    controller = ChromaController(persist_directory=chroma_dir)
    embedder = OllamaEmbeddingWrapper(base_url=ollama_url)

    git: GitPipeline | None = None
    if git_path:
        try:
            git = GitPipeline(repo_path=git_path)
            logger.info("GitPipeline attached: %s (branch: %s)", git_path, git.current_branch())
        except GitPipelineError as exc:
            logger.warning(
                "GitPipeline init failed for '%s': %s -- running without Git support.",
                git_path, exc,
            )

    return IngestionCoordinator(
        controller=controller,
        embedder=embedder,
        git_pipeline=git,
    )


def run_daemon(
    watch_paths: list[str],
    coordinator: IngestionCoordinator,
    debounce_seconds: float,
) -> NoReturn:
    """
    Wire WorkspaceFileWatcher to IngestionCoordinator and block until stopped.

    Exact constructor call matches the v0.2 interface spec::

        WorkspaceFileWatcher(
            watch_paths        = [...],
            on_code_change     = Callable[[FileChangeEvent], None],
            on_telemetry_event = Callable[[FileChangeEvent], None],
            debounce_seconds   = float,
        )

    Parameters
    ----------
    watch_paths:
        List of absolute directory paths to monitor.
    coordinator:
        Fully built IngestionCoordinator instance.
    debounce_seconds:
        Debounce window forwarded verbatim to WorkspaceFileWatcher.
    """
    on_code_change = _make_on_code_change(coordinator)
    on_telemetry_event = _make_on_telemetry_event(coordinator)

    watcher = WorkspaceFileWatcher(
        watch_paths=watch_paths,
        on_code_change=on_code_change,
        on_telemetry_event=on_telemetry_event,
        debounce_seconds=debounce_seconds,
    )

    # Graceful shutdown on SIGINT / SIGTERM
    def _shutdown(signum, frame):
        print("\n[watch_daemon] Stopping watcher...", flush=True)
        watcher.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    watcher.start()

    paths_display = ", ".join(watch_paths)
    print(
        f"[watch_daemon] Watching: {paths_display}\n"
        f"[watch_daemon] Debounce: {debounce_seconds}s | Press Ctrl-C to stop.",
        flush=True,
    )

    # Keep the main thread alive; watcher runs in a daemon background thread.
    while watcher.is_running():
        time.sleep(0.5)

    # Should not normally be reached (shutdown via signal).
    sys.exit(0)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m abm.companion.watch_daemon",
        description=(
            "ABM v0.2 Watch Daemon -- monitors workspace file changes and "
            "ingests them into the correct ChromaDB memory stream."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m abm.companion.watch_daemon --path ./my_project\n"
            "  python -m abm.companion.watch_daemon --path ./src --path ./lib "
            "--debounce 2.0 --git-path .\n"
        ),
    )
    parser.add_argument(
        "--path",
        dest="paths",
        action="append",
        metavar="DIR",
        required=True,
        help=(
            "Directory to watch (absolute or relative to cwd). "
            "Repeat this flag to watch multiple directories."
        ),
    )
    parser.add_argument(
        "--debounce",
        dest="debounce",
        type=float,
        default=1.0,
        metavar="SECONDS",
        help="Debounce window in seconds (default: 1.0).",
    )
    parser.add_argument(
        "--chroma-dir",
        dest="chroma_dir",
        default="./memory/chroma_store",
        metavar="DIR",
        help="ChromaDB persistence directory (default: ./memory/chroma_store).",
    )
    parser.add_argument(
        "--ollama-url",
        dest="ollama_url",
        default="http://127.0.0.1:11434",
        metavar="URL",
        help="Ollama base URL (default: http://127.0.0.1:11434).",
    )
    parser.add_argument(
        "--git-path",
        dest="git_path",
        default=None,
        metavar="DIR",
        help=(
            "Path to a local Git repository to attach a GitPipeline. "
            "If omitted, Git-based ingestion is disabled (file-change ingestion "
            "is unaffected)."
        ),
    )
    parser.add_argument(
        "--log-level",
        dest="log_level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """
    CLI entry point.  Resolves all paths, builds the object graph, then
    delegates to ``run_daemon()`` which blocks until shutdown.
    """
    args = _parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s  %(levelname)-8s  %(name)s -- %(message)s",
        datefmt="%H:%M:%S",
    )

    # Resolve and validate watch paths
    resolved_paths: list[str] = []
    for raw in args.paths:
        p = Path(raw).resolve()
        if not p.is_dir():
            print(
                f"[watch_daemon] ERROR: watch path does not exist or is not a directory: '{p}'",
                file=sys.stderr,
                flush=True,
            )
            sys.exit(1)
        resolved_paths.append(str(p))

    # Resolve optional git path
    git_path: str | None = None
    if args.git_path:
        gp = Path(args.git_path).resolve()
        git_path = str(gp)

    print("[watch_daemon] Initialising ChromaDB and Ollama embedder...", flush=True)
    coordinator = build_coordinator(
        chroma_dir=args.chroma_dir,
        ollama_url=args.ollama_url,
        git_path=git_path,
    )
    print("[watch_daemon] Object graph ready.", flush=True)

    run_daemon(
        watch_paths=resolved_paths,
        coordinator=coordinator,
        debounce_seconds=args.debounce,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
