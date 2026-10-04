"""
abm/clients/console/commands.py
=================================
Console command handlers — the bridge between parsed CLI arguments and the
ABM API layer.

Each ``cmd_*`` function:
  1. Accepts only plain Python scalars (str, int) as arguments.
  2. Calls exactly one API capability function with those arguments.
  3. Passes the result to the corresponding formatter.
  4. Returns a formatted string to main.py for printing.

Design contract:
  - No cmd_* function calls internal ABM modules directly.
  - No cmd_* function owns any state.
  - All error handling is delegated to the API layer (which degrades
    gracefully per constitution rule 9). The command handlers surface
    errors as readable strings if the API propagates one unexpectedly.
  - Exactly six commands are implemented: ask, search, status, summarize,
    memory, explain.
  - ``continue``, ``reflect``, ``plan``, ``learn`` are NOT implemented here —
    their future stubs live in abm.api.capabilities and are documented in
    ARCHITECTURE_BACKLOG.md and CLIENT_01_CONSOLE.md.
"""

from __future__ import annotations

import logging

from abm.api.capabilities import (
    aggregateProjectMemory,
    answerQuestion,
    explainAuditRecord,
    getSystemStatus,
    retrieveKnowledge,
    runTask,
    ingestDocument,
    reviewProject,
)
from abm.api.core.registry import ServiceRegistry
from abm.clients.console.formatter import (
    format_ask,
    format_explain,
    format_memory,
    format_search,
    format_status,
    format_summarize,
    format_run,
    format_ingest,
    format_review,
)

logger = logging.getLogger(__name__)


def cmd_ask(question: str, *, registry: ServiceRegistry, history: list[dict[str, str]] | None = None) -> str:
    """
    ``ask <question>`` — route through the v0.3 router, retrieve from
    the department's allowed streams, return formatted hits.

    Wires to: ``answerQuestion`` (stable)
    """
    logger.debug("cmd_ask: question=%r", question)
    try:
        result = answerQuestion(question, registry=registry, history=history)
        
        if history is not None:
            history.append({"role": "user", "content": question})
            history.append({"role": "agent", "content": result.synthesis})
            # Keep only the last 3 exchanges (6 items)
            del history[:-6]
            
        return format_ask(result)
    except Exception as exc:
        logger.error("cmd_ask: unexpected error — %s", exc)
        return f"[ask error]: {exc}"


def cmd_search(query: str, *, registry: ServiceRegistry) -> str:
    """
    ``search <query>`` — direct semantic search across all four memory streams.

    Wires to: ``retrieveKnowledge`` (stable)
    """
    logger.debug("cmd_search: query=%r", query)
    try:
        result = retrieveKnowledge(query, registry=registry)
        return format_search(result)
    except Exception as exc:
        logger.error("cmd_search: unexpected error — %s", exc)
        return f"[search error]: {exc}"


def cmd_status(*, registry: ServiceRegistry) -> str:
    """
    ``status`` — read-only system and workflow state view.

    Wires to: ``getSystemStatus`` (stable)
    """
    logger.debug("cmd_status: querying system status")
    try:
        result = getSystemStatus(registry=registry)
        return format_status(result)
    except Exception as exc:
        logger.error("cmd_status: unexpected error — %s", exc)
        return f"[status error]: {exc}"


def cmd_summarize(project: str, *, registry: ServiceRegistry) -> str:
    """
    ``summarize <project>`` — strategic asset analysis for a project from memory.

    Wires to: ``summarizeProject`` (stable)
    """
    logger.debug("cmd_summarize: project=%r", project)
    try:
        result = summarizeProject(project, registry=registry)
        return format_summarize(result)
    except (ValueError, RuntimeError) as exc:
        # ValueError: empty project name; RuntimeError: Ollama unavailable
        logger.warning("cmd_summarize: %s", exc)
        return (
            f"[summarize]: Cannot summarize '{project}': {exc}\n"
            "Ensure Ollama is running at 127.0.0.1:11434."
        )
    except Exception as exc:
        logger.error("cmd_summarize: unexpected error — %s", exc)
        return f"[summarize error]: {exc}"


def cmd_memory(project: str, *, registry: ServiceRegistry) -> str:
    """
    ``memory <project>`` — aggregated read-only view across all four streams
    filtered by project name.

    Wires to: ``aggregateProjectMemory`` (stable)
    """
    logger.debug("cmd_memory: project=%r", project)
    try:
        result = aggregateProjectMemory(project, registry=registry)
        return format_memory(result)
    except Exception as exc:
        logger.error("cmd_memory: unexpected error — %s", exc)
        return f"[memory error]: {exc}"


def cmd_explain(target: str, *, registry: ServiceRegistry) -> str:
    """
    ``explain <target>`` — format recorded audit data for a past action.

    Looks up by contract_id prefix (WorkflowMonitor) and by keyword in
    decision journal entries (Stream D).

    Wires to: ``explainAuditRecord`` (stable)
    """
    logger.debug("cmd_explain: target=%r", target)
    try:
        result = explainAuditRecord(target, registry=registry)
        return format_explain(result)
    except Exception as exc:
        logger.error("cmd_explain: unexpected error — %s", exc)
        return f"[explain error]: {exc}"


def cmd_run(objective: str, *, registry: ServiceRegistry) -> str:
    """
    ``run <objective>`` — classify a task, assign it to a worker sandbox, 
    and execute it in the background.

    Wires to: ``runTask`` (stable)
    """
    logger.debug("cmd_run: objective=%r", objective)
    try:
        result = runTask(objective, registry=registry)
        return format_run(result)
    except Exception as exc:
        logger.error("cmd_run: unexpected error — %s", exc)
        return f"[run error]: {exc}"


def cmd_ingest(path: str, *, registry: ServiceRegistry) -> str:
    """
    ``ingest <path>`` — manually ingest a document or directory into ABM streams.

    Wires to: ``ingestDocument`` (stable)
    """
    logger.debug("cmd_ingest: path=%r", path)
    try:
        result = ingestDocument(path, registry=registry)
        return format_ingest(result)
    except Exception as exc:
        logger.error("cmd_ingest: unexpected error — %s", exc)
        return f"[ingest error]: {exc}"


def cmd_review(project: str, *, registry: ServiceRegistry) -> str:
    """
    ``review <project>`` — retrieves a project's Stream A entries and synthesizes 
    actionable improvement suggestions grounded strictly in what was actually ingested.

    Wires to: ``reviewProject`` (stable)
    """
    logger.debug("cmd_review: project=%r", project)
    try:
        result = reviewProject(project, registry=registry)
        return format_review(result)
    except Exception as exc:
        logger.error("cmd_review: unexpected error — %s", exc)
        return f"[review error]: {exc}"


__all__ = [
    "cmd_ask",
    "cmd_search",
    "cmd_status",
    "cmd_summarize",
    "cmd_memory",
    "cmd_explain",
    "cmd_run",
    "cmd_ingest",
    "cmd_review",
]
