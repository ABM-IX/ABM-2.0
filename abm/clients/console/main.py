"""
abm/clients/console/main.py
=============================
ABM Console — Client #1 (Interim Interaction Shell)

Entry point for the ABM console client. Implements exactly six commands
wired to stable API capabilities:

    ask <question>      — route + retrieve from relevant memory streams
    search <query>      — direct search across all four streams
    status              — read-only workflow and system state
    summarize <project> — strategic asset analysis from memory
    memory <project>    — aggregated memory view for a project
    explain <target>    — formatted audit record for a past action

Architecture:
  All commands communicate exclusively through the ``abm.api`` layer — this
  module never imports from ``abm.memory``, ``abm.orchestrator``, or any
  other internal module directly. (Architectural Constitution rule 13.)

Boot sequence:
  1. Parse arguments (argparse).
  2. Create APIConfig (uses defaults — all paths match repo layout).
  3. Create ServiceRegistry and call boot().
  4. Dispatch to the matching cmd_* handler.
  5. Print result to stdout.
  6. Call registry.shutdown() before exit.

Graceful degradation (constitution rule 9):
  If Ollama is unreachable the system still boots and most commands return
  partial results with a degraded warning rather than crashing.

Usage:
    python -m abm.clients.console.main ask "what is ABM?"
    python -m abm.clients.console.main search "BLoC pattern"
    python -m abm.clients.console.main status
    python -m abm.clients.console.main summarize smart_transit
    python -m abm.clients.console.main memory houseconnect
    python -m abm.clients.console.main explain TXN_12345
"""

from __future__ import annotations

import argparse
import logging
import shlex
import sys

from abm.api.core.config import APIConfig
from abm.api.core.registry import ServiceRegistry
from abm.clients.console.commands import (
    cmd_ask,
    cmd_explain,
    cmd_memory,
    cmd_search,
    cmd_status,
    cmd_summarize,
    cmd_run,
    cmd_ingest,
    cmd_review,
)

# ──────────────────────────────────────────────────────────────────────────────
# Logging setup
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.WARNING,          # Quiet by default; --verbose raises to DEBUG
    format="%(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Argument parser
# ──────────────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="abm",
        description=(
            "ABM Console — interim interaction shell for the Cognitive OS.\n"
            "All commands route through the ABM API layer.\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  abm ask \"what is ABM?\"\n"
            "  abm search \"BLoC pattern\"\n"
            "  abm status\n"
            "  abm summarize smart_transit\n"
            "  abm memory houseconnect\n"
            "  abm explain TXN_12345\n"
            "\n"
            "Not in scope (no backend engine yet):\n"
            "  continue, reflect, plan, learn\n"
            "  See ARCHITECTURE_BACKLOG.md and CLIENT_01_CONSOLE.md.\n"
        ),
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable DEBUG logging.",
    )
    parser.add_argument(
        "--chroma-dir",
        default=None,
        metavar="PATH",
        help="Override ChromaDB persist directory (default: ./memory/chroma_store).",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    subparsers.required = True

    # ask
    ask_p = subparsers.add_parser(
        "ask",
        help="Route a question through the classifier and retrieve from memory.",
    )
    ask_p.add_argument("question", nargs="+", help="The question to ask.")

    # run
    run_p = subparsers.add_parser(
        "run",
        help="Classify a task and dispatch it to a worker sandbox.",
    )
    run_p.add_argument("description", nargs="+", help="The task description.")

    # search
    search_p = subparsers.add_parser(
        "search",
        help="Direct semantic search across all four memory streams.",
    )
    search_p.add_argument("query", nargs="+", help="The search query.")

    # status
    subparsers.add_parser(
        "status",
        help="Read-only view of system health and in-flight workflow state.",
    )

    # summarize
    summarize_p = subparsers.add_parser(
        "summarize",
        help="Strategic asset analysis for a project from memory.",
    )
    summarize_p.add_argument("project", nargs="+", help="Project name to summarize.")

    # memory
    memory_p = subparsers.add_parser(
        "memory",
        help="Aggregated read-only memory view for a project across all streams.",
    )
    memory_p.add_argument("project", nargs="+", help="Project name to inspect.")

    # explain
    explain_p = subparsers.add_parser(
        "explain",
        help="Formatted audit record for a past action (contract_id or keyword).",
    )
    explain_p.add_argument("target", nargs="+", help="Contract ID prefix or keyword.")

    # ingest
    ingest_p = subparsers.add_parser(
        "ingest",
        help="Manually ingest a file or directory into ABM streams.",
    )
    ingest_p.add_argument("path", help="Path to file or directory.")

    # review
    review_p = subparsers.add_parser(
        "review",
        help="Retrieve a project's Code Topologies and synthesize actionable improvement suggestions.",
    )
    review_p.add_argument("project", nargs="+", help="Project name to review.")

    return parser


# ──────────────────────────────────────────────────────────────────────────────
# Dispatch & REPL
# ──────────────────────────────────────────────────────────────────────────────

def _dispatch(args: argparse.Namespace, registry: ServiceRegistry, session_history: list[dict[str, str]] | None = None) -> str:
    cmd = args.command
    if cmd == "ask":
        question = " ".join(args.question)
        return cmd_ask(question, registry=registry, history=session_history)
    elif cmd == "run":
        description = " ".join(args.description)
        return cmd_run(description, registry=registry)
    elif cmd == "search":
        query = " ".join(args.query)
        return cmd_search(query, registry=registry)
    elif cmd == "status":
        return cmd_status(registry=registry)
    elif cmd == "summarize":
        project = " ".join(args.project)
        return cmd_summarize(project, registry=registry)
    elif cmd == "memory":
        project = " ".join(args.project)
        return cmd_memory(project, registry=registry)
    elif cmd == "explain":
        target = " ".join(args.target)
        return cmd_explain(target, registry=registry)
    elif cmd == "ingest":
        return cmd_ingest(args.path, registry=registry)
    elif cmd == "review":
        project = " ".join(args.project)
        return cmd_review(project, registry=registry)
    else:
        print(f"[abm] Unknown command: {cmd}", file=sys.stderr)
        return ""


def _repl_mode(registry: ServiceRegistry, parser: argparse.ArgumentParser) -> int:
    print("Starting ABM Console REPL. Type 'exit' or press Ctrl+C to quit.")
    session_history = []
    try:
        while True:
            try:
                line = input("ABM> ").strip()
            except EOFError:
                print()
                break
                
            if not line:
                continue
                
            if line.lower() in ("exit", "quit"):
                break
                
            args_list = line.split(maxsplit=1)
                
            try:
                args = parser.parse_args(args_list)
            except SystemExit:
                # argparse prints usage and calls exit(), we just catch it to keep REPL alive
                continue
                
            output = _dispatch(args, registry, session_history)
            if output:
                print(output)
    except KeyboardInterrupt:
        print("\n[abm] Interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        logger.error("Unhandled error in REPL: %s", exc, exc_info=True)
        print(f"\n[abm] Error: {exc}\n", file=sys.stderr)
        return 1
    finally:
        registry.shutdown()
        
    return 0


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    """
    Entry point.  Returns the process exit code (0 = success, 1 = error).
    """
    # Fix UnicodeEncodeError when printing '─' or '█' on Windows consoles
    if sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')

    if argv is None:
        argv = sys.argv[1:]

    is_repl = len(argv) == 0

    parser = _build_parser()
    
    # In REPL mode, we don't pass argv to parse_args here
    if not is_repl:
        # If not REPL, parser might exit on invalid args. That is expected.
        try:
            args = parser.parse_args(argv)
        except SystemExit as e:
            return e.code

    # Verbose logging (only applies if we parsed one-shot args, REPL defaults to standard)
    if not is_repl and args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Verbose mode enabled.")

    # Build config
    config = APIConfig()
    if not is_repl and getattr(args, 'chroma_dir', None):
        config = APIConfig(chroma_persist_directory=args.chroma_dir)

    # Boot registry (constitution rule 9: degrade, don't crash on Ollama-down)
    registry = ServiceRegistry(config)
    try:
        registry.boot()
    except RuntimeError as exc:
        print(f"\n[abm] Boot failed: {exc}\n", file=sys.stderr)
        return 1

    if is_repl:
        return _repl_mode(registry, parser)

    # One-shot dispatch
    try:
        output = _dispatch(args, registry)
    except KeyboardInterrupt:
        print("\n[abm] Interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        logger.error("Unhandled error in command dispatch: %s", exc, exc_info=True)
        print(f"\n[abm] Error: {exc}\n", file=sys.stderr)
        return 1
    finally:
        registry.shutdown()

    if output:
        print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
