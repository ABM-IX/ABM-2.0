"""
abm/api/capabilities.py
========================
ABM Capability Catalogue — Client #1 (Console + API Layer)

Every capability the ABM engine exposes to clients is declared here as a
module-level function.  Each capability carries three metadata tags in its
docstring header:

    STATUS       : stable | experimental | future
    OWNER        : the primary backend module that implements the logic
    DEPENDENCIES : services consumed from ServiceRegistry
    CONSUMERS    : which clients are wired to this capability

Naming follows Architectural Constitution rule 14 — capability-oriented
names that survive refactoring (``answerQuestion``, not ``router.classify``).

────────────────────────────────────────────────────────────────────────────
STABLE  — tested, gated v0.1–v0.5 backends, wired to console commands now.
EXPERIMENTAL — built but not yet wired to any client.
FUTURE  — documented placeholder; no backend exists yet (see ARCHITECTURE_BACKLOG.md).
────────────────────────────────────────────────────────────────────────────

Design contract:
  - All functions accept a ``ServiceRegistry`` as their first keyword arg.
  - All functions degrade gracefully when Ollama is unavailable (constitution
    rule 9) — they return a typed result with a ``degraded`` flag or a
    descriptive string rather than raising to the client.
  - No function writes to persistent state except ``recordDecision`` (future).
  - Return types are either plain dataclasses or strings — no raw ChromaDB
    internals leak through to clients.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from abm.memory.chroma_controller import ALL_COLLECTIONS
from abm.orchestrator.departments import DEPARTMENT_REGISTRY
from abm.strategic_wing.strategic_asset_analyzer import StrategicAnalysisResult
from abm.mobile.event_models import AmbientEvent
from abm.mobile.stream_c_writer import WriteResult

from .core.registry import ServiceRegistry

logger = logging.getLogger(__name__)


# ============================================================================
# Shared return types
# ============================================================================


@dataclass
class AnswerResult:
    """
    Return type for ``answerQuestion``.

    Attributes
    ----------
    question : str
        The original question as submitted.
    department : str
        The department the router classified this question into.
    confidence : str
        Routing confidence: ``"high"``, ``"medium"``, or ``"low"``.
    hits : list[dict[str, Any]]
        Retrieved memory items relevant to the question, drawn from the
        department's allowed streams.  Each item has ``text``, ``collection``,
        ``distance``, and ``metadata`` keys.
    fallback_used : bool
        True if the router defaulted to software_engineering because Ollama
        was unreachable or classification failed.
    degraded : bool
        True if Ollama was not reachable during retrieval.
    """

    question: str
    department: str
    confidence: str
    hits: list[dict[str, Any]] = field(default_factory=list)
    fallback_used: bool = False
    degraded: bool = False


@dataclass
class KnowledgeResult:
    """
    Return type for ``retrieveKnowledge``.

    Attributes
    ----------
    query : str
        The original search query.
    hits : list[dict[str, Any]]
        Retrieved items across all streams, sorted by distance.
        Each item has ``text``, ``collection``, ``distance``, ``metadata``.
    degraded : bool
        True if Ollama was not reachable.
    """

    query: str
    hits: list[dict[str, Any]] = field(default_factory=list)
    degraded: bool = False


@dataclass
class StatusResult:
    """
    Return type for ``getSystemStatus``.

    Attributes
    ----------
    overview : str
        Human-readable workflow overview from WorkflowMonitor.
    quarantined_ids : list[str]
        Contract IDs whose quarantine files were found on disk.
    ollama_reachable : bool
    chroma_ready : bool
    degraded : bool
    """

    overview: str
    quarantined_ids: list[str] = field(default_factory=list)
    ollama_reachable: bool = False
    chroma_ready: bool = False
    degraded: bool = True


@dataclass
class MemoryResult:
    """
    Return type for ``aggregateProjectMemory``.

    Attributes
    ----------
    project_name : str
        The project filter that was applied.
    streams : dict[str, list[dict[str, Any]]]
        Per-stream retrieval results. Keys are collection names.
        Values are lists of ``{text, distance, metadata}`` dicts.
    total_hits : int
        Sum of all items across all streams.
    degraded : bool
        True if Ollama was not reachable.
    """

    project_name: str
    streams: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    total_hits: int = 0
    degraded: bool = False


@dataclass
class ExplainResult:
    """
    Return type for ``explainAuditRecord``.

    Attributes
    ----------
    target : str
        The audit target that was looked up.
    found : bool
        True if at least one record was found.
    records : list[dict[str, Any]]
        Formatted audit records.  Each has a ``source`` key
        (``"monitor"`` or ``"decision_journal"``) plus relevant fields.
    notes : str
        Human-readable explanation summary.
    """

    target: str
    found: bool = False
    records: list[dict[str, Any]] = field(default_factory=list)
    notes: str = ""


# ============================================================================
# Internal helpers
# ============================================================================


def _flatten_query_hits(
    registry: ServiceRegistry,
    collection_name: str,
    query_embedding: list[float],
    n_results: int,
) -> list[dict[str, Any]]:
    """
    Query a single ChromaDB collection and return flat hit dicts.
    Returns an empty list on any error.
    """
    try:
        result = registry.controller.query_collection(
            collection_name=collection_name,
            query_embedding=query_embedding,
            n_results=n_results,
        )
        ids = result.ids[0] if result.ids else []
        docs = result.documents[0] if result.documents else []
        metas = result.metadatas[0] if result.metadatas else []
        dists = result.distances[0] if result.distances else []
        hits = []
        for i, doc_id in enumerate(ids):
            hits.append({
                "id": doc_id,
                "text": docs[i] if i < len(docs) else "",
                "collection": collection_name,
                "distance": dists[i] if i < len(dists) else None,
                "metadata": dict(metas[i]) if i < len(metas) else {},
            })
        return hits
    except Exception as exc:
        logger.debug("_flatten_query_hits(%s): %s", collection_name, exc)
        return []


# ============================================================================
# ── STABLE CAPABILITIES ──────────────────────────────────────────────────────
# These are tested, gated, and wired to console commands.
# ============================================================================


def answerQuestion(
    question: str,
    *,
    registry: ServiceRegistry,
    n_results: int | None = None,
) -> AnswerResult:
    """
    Route a natural-language question through the classification engine and
    retrieve relevant memory from the department's allowed streams.

    STATUS       : stable
    OWNER        : abm.orchestrator.router.ClassificationRouter
    DEPENDENCIES : ServiceRegistry.router, ServiceRegistry.embedder,
                   ServiceRegistry.controller
    CONSUMERS    : console ``ask`` command

    The router classifies the question to a Department (v0.3). The
    department's ``allowed_streams`` scope the retrieval — only the streams
    relevant to that department are queried, keeping the answer grounded in
    the right memory layer. This is a direct passthrough: classify → scope
    → retrieve. No new engine is introduced.

    Degrades gracefully when Ollama is unreachable: the router's built-in
    fallback returns ``department=software_engineering`` with
    ``confidence="low"`` and ``fallback_used=True``.  Retrieval is then
    attempted; if the embedder is also unavailable the hits list will be
    empty and ``degraded=True``.

    Parameters
    ----------
    question : str
        The question to answer. Must be non-empty.
    registry : ServiceRegistry
        Booted service registry.
    n_results : int, optional
        Results per stream. Defaults to ``registry.config.n_retrieval_results``.

    Returns
    -------
    AnswerResult
    """
    if not question or not question.strip():
        return AnswerResult(
            question=question,
            department="software_engineering",
            confidence="low",
            fallback_used=True,
            degraded=False,
        )

    n = n_results if n_results is not None else registry.config.n_retrieval_results

    # Step 1: classify → RouterResult (never raises)
    router_result = registry.router.classify(question)
    department_str = router_result.contract.department.value
    confidence = router_result.confidence_hint
    fallback = router_result.fallback_used

    # Step 2: scope streams to the classified department
    sandbox = DEPARTMENT_REGISTRY[router_result.contract.department]
    allowed_streams = list(sandbox.allowed_streams)

    # Step 3: embed the question and query scoped streams
    hits: list[dict[str, Any]] = []
    degraded = False
    try:
        embedding = registry.embedder.embed(question)
        for collection_name in allowed_streams:
            hits.extend(
                _flatten_query_hits(registry, collection_name, embedding, n)
            )
        # Sort by distance (ascending)
        hits.sort(key=lambda h: float("inf") if h["distance"] is None else h["distance"])
    except Exception as exc:
        logger.warning("answerQuestion: retrieval failed — %s", exc)
        degraded = True

    return AnswerResult(
        question=question,
        department=department_str,
        confidence=confidence,
        hits=hits,
        fallback_used=fallback,
        degraded=degraded,
    )


def retrieveKnowledge(
    query: str,
    *,
    registry: ServiceRegistry,
    n_results: int | None = None,
) -> KnowledgeResult:
    """
    Direct semantic search across all four memory streams.

    STATUS       : stable
    OWNER        : abm.memory.chroma_controller.ChromaController
    DEPENDENCIES : ServiceRegistry.embedder, ServiceRegistry.controller
    CONSUMERS    : console ``search`` command

    Unlike ``answerQuestion``, this capability does not classify the query.
    It embeds it and runs the same vector query against every stream, then
    returns hits sorted by distance. This gives the user raw access to
    everything in memory without the routing filter.

    Degrades gracefully when Ollama is unreachable: returns an empty hits
    list with ``degraded=True``.

    Parameters
    ----------
    query : str
        The search query. Must be non-empty.
    registry : ServiceRegistry
        Booted service registry.
    n_results : int, optional
        Results per stream. Defaults to ``registry.config.n_retrieval_results``.

    Returns
    -------
    KnowledgeResult
    """
    if not query or not query.strip():
        return KnowledgeResult(query=query, degraded=False)

    n = n_results if n_results is not None else registry.config.n_retrieval_results
    hits: list[dict[str, Any]] = []
    degraded = False

    try:
        embedding = registry.embedder.embed(query)
        for collection_name in ALL_COLLECTIONS:
            hits.extend(
                _flatten_query_hits(registry, collection_name, embedding, n)
            )
        hits.sort(key=lambda h: float("inf") if h["distance"] is None else h["distance"])
    except Exception as exc:
        logger.warning("retrieveKnowledge: embedding/retrieval failed — %s", exc)
        degraded = True

    return KnowledgeResult(query=query, hits=hits, degraded=degraded)


def getSystemStatus(*, registry: ServiceRegistry) -> StatusResult:
    """
    Read-only view of current system and workflow state.

    STATUS       : stable
    OWNER        : abm.strategic_wing.workflow_monitor.WorkflowMonitor
    DEPENDENCIES : ServiceRegistry.monitor, ServiceRegistry.health_check()
    CONSUMERS    : console ``status`` command

    Aggregates:
      - WorkflowMonitor.get_overview_report() — in-memory task state summary
        for all tasks registered in the current session.
      - WorkflowMonitor.scan_quarantine_directory() — disk scan for quarantine
        files from v0.4, including any from prior sessions.
      - ServiceRegistry.health_check() — Ollama + ChromaDB readiness.

    Never raises. Follows constitution rule 9.

    Parameters
    ----------
    registry : ServiceRegistry
        Booted service registry.

    Returns
    -------
    StatusResult
    """
    try:
        quarantined_ids = registry.monitor.scan_quarantine_directory()
        overview = registry.monitor.get_overview_report()
    except Exception as exc:
        logger.warning("getSystemStatus: monitor error — %s", exc)
        quarantined_ids = []
        overview = f"[monitor error: {exc}]"

    health = registry.health_check()

    return StatusResult(
        overview=overview,
        quarantined_ids=quarantined_ids,
        ollama_reachable=health.ollama_reachable,
        chroma_ready=health.chroma_ready,
        degraded=health.degraded,
    )


def summarizeProject(
    project_name: str,
    *,
    registry: ServiceRegistry,
    n_results_per_stream: int = 3,
) -> StrategicAnalysisResult:
    """
    Produce a read-only strategic analysis of a project from memory.

    STATUS       : stable
    OWNER        : abm.strategic_wing.strategic_asset_analyzer.StrategicAssetAnalyzer
    DEPENDENCIES : ServiceRegistry.analyzer (→ embedder + controller)
    CONSUMERS    : console ``summarize`` command

    Delegates entirely to ``StrategicAssetAnalyzer.analyze()``.  The
    analyzer queries all four streams with the project name as the query,
    groups retrieved context by stream, and maps it into strategic option
    paths.  It never writes to memory (constitution rule 2).

    Parameters
    ----------
    project_name : str
        Name of the project to summarize. Used as the analysis query.
    registry : ServiceRegistry
        Booted service registry.
    n_results_per_stream : int
        Results per stream. Default: 3.

    Returns
    -------
    StrategicAnalysisResult
        ``decision_recorded`` is always ``False`` per the analyzer contract.

    Raises
    ------
    ValueError
        If ``project_name`` is empty (propagated from analyzer).
    RuntimeError
        If Ollama is unreachable (propagated from embedder).
    """
    return registry.analyzer.analyze(
        query=project_name,
        n_results_per_stream=n_results_per_stream,
    )


def aggregateProjectMemory(
    project_name: str,
    *,
    registry: ServiceRegistry,
    n_results: int | None = None,
) -> MemoryResult:
    """
    Read-only aggregated memory view for a project across all four streams.

    STATUS       : stable
    OWNER        : abm.memory.chroma_controller.ChromaController
    DEPENDENCIES : ServiceRegistry.embedder, ServiceRegistry.controller
    CONSUMERS    : console ``memory`` command

    Embeds the project name and queries all four streams independently,
    returning results grouped by stream (decisions, docs, conversations,
    files/code, timeline). No new engine — this is a composed retrieval
    view over the existing ChromaDB data as specified in CLIENT_01_CONSOLE.md.

    Degrades gracefully when Ollama is unreachable.

    Parameters
    ----------
    project_name : str
        Project name used as the retrieval query.
    registry : ServiceRegistry
        Booted service registry.
    n_results : int, optional
        Results per stream. Defaults to ``registry.config.n_retrieval_results``.

    Returns
    -------
    MemoryResult
    """
    if not project_name or not project_name.strip():
        return MemoryResult(project_name=project_name, degraded=False)

    n = n_results if n_results is not None else registry.config.n_retrieval_results
    streams: dict[str, list[dict[str, Any]]] = {}
    total = 0
    degraded = False

    try:
        embedding = registry.embedder.embed(project_name)
        for collection_name in ALL_COLLECTIONS:
            hits = _flatten_query_hits(registry, collection_name, embedding, n)
            streams[collection_name] = hits
            total += len(hits)
    except Exception as exc:
        logger.warning("aggregateProjectMemory: failed — %s", exc)
        degraded = True

    return MemoryResult(
        project_name=project_name,
        streams=streams,
        total_hits=total,
        degraded=degraded,
    )


def explainAuditRecord(
    target: str,
    *,
    registry: ServiceRegistry,
) -> ExplainResult:
    """
    Format already-recorded audit data for a past action in human-readable form.

    STATUS       : stable
    OWNER        : abm.strategic_wing.workflow_monitor.WorkflowMonitor
                   (monitor layer), abm.memory.chroma_controller.ChromaController
                   (Stream D for decision journal entries)
    DEPENDENCIES : ServiceRegistry.monitor, ServiceRegistry.embedder,
                   ServiceRegistry.controller
    CONSUMERS    : console ``explain`` command

    Two sources are consulted, matching the audit data that constitution
    rule 5 mandates must always be recorded:

    Source A — WorkflowMonitor (in-memory, live-session scope):
      Looks up ``target`` as a contract_id prefix among registered tasks.
      Each TaskRecord exposes: routing classification, confidence_hint,
      v0.4 gate scores (confidence_score, quarantine_flag), task state,
      and the objective string.

    Source B — ChromaDB Stream D (persisted, cross-session):
      Embeds ``target`` and queries ``abm_cognitive_identity`` for decision
      journal entries whose text contains the target string. Returns
      STRATEGIC DECISION RECORD entries written by DecisionJournal.log_decision().

    Both sources are searched; results from both are returned together.
    This is not a new engine — the data is already recorded per constitution
    rule 5; this capability makes it readable.

    Parameters
    ----------
    target : str
        A contract_id prefix (e.g. ``TXN_12345``) or a keyword that appears
        in a decision journal entry text.
    registry : ServiceRegistry
        Booted service registry.

    Returns
    -------
    ExplainResult
    """
    if not target or not target.strip():
        return ExplainResult(
            target=target,
            found=False,
            notes="No target specified.",
        )

    records: list[dict[str, Any]] = []

    # ── Source A: WorkflowMonitor (in-memory task records) ───────────────────
    try:
        monitor = registry.monitor
        # Sync disk quarantine state before reading
        monitor.scan_quarantine_directory()

        for contract_id, task_record in monitor._registry.items():  # noqa: SLF001
            if target.lower() in contract_id.lower():
                entry: dict[str, Any] = {
                    "source": "monitor",
                    "contract_id": contract_id,
                    "objective": task_record.contract.objective,
                    "department": task_record.contract.department.value,
                    "state": task_record.state.value,
                }
                if task_record.gate_result is not None:
                    g = task_record.gate_result
                    entry["gate_passed"] = g.passed
                    entry["confidence_score"] = round(g.confidence_score, 4)
                    entry["quarantine_flag"] = g.quarantine_flag
                    entry["gate_reason"] = g.reason
                if task_record.execution_result is not None:
                    e = task_record.execution_result
                    entry["exit_code"] = e.exit_code
                    entry["execution_time_ms"] = e.execution_time_ms
                records.append(entry)
    except Exception as exc:
        logger.warning("explainAuditRecord: monitor lookup failed — %s", exc)

    # ── Source B: ChromaDB Stream D (persisted decision journal entries) ──────
    try:
        embedding = registry.embedder.embed(target)
        hits = _flatten_query_hits(
            registry,
            "abm_cognitive_identity",
            embedding,
            n_results=5,
        )
        for hit in hits:
            # Filter: decision journal entries start with "STRATEGIC DECISION RECORD"
            if "STRATEGIC DECISION RECORD" in hit.get("text", ""):
                records.append({
                    "source": "decision_journal",
                    "doc_id": hit["id"],
                    "text": hit["text"],
                    "distance": hit["distance"],
                    "metadata": hit["metadata"],
                })
    except Exception as exc:
        logger.warning("explainAuditRecord: Stream D lookup failed — %s", exc)

    found = len(records) > 0
    notes = (
        f"Found {len(records)} audit record(s) for target '{target}'."
        if found
        else f"No audit records found for target '{target}'. "
             "Monitor records are session-scoped; decision journal entries "
             "require the target text to appear in a DECISION record."
    )

    return ExplainResult(
        target=target,
        found=found,
        records=records,
        notes=notes,
    )


# ============================================================================
# ── STABLE: Phase v1.0 — Ambient Interaction ─────────────────────────────────
# ============================================================================


@dataclass
class AmbientIngestionResult:
    """
    Return type for ``ingestAmbientEvent``.

    Attributes
    ----------
    status : str
        ``"ok"`` | ``"compressed"`` | ``"invalid"`` | ``"error"``.
    doc_id : str
        ChromaDB document ID written (empty on non-ok statuses).
    reason : str
        Human-readable explanation (empty on ``"ok"``).
    housekeeper_ran : bool
        ``True`` if a retention housekeeping pass ran during this write.
    degraded : bool
        ``True`` if the manager was unavailable (Ollama down, etc.).
    """

    status: str
    doc_id: str = ""
    reason: str = ""
    housekeeper_ran: bool = False
    degraded: bool = False


def ingestAmbientEvent(
    event: "AmbientEvent",
    *,
    registry: ServiceRegistry,
) -> AmbientIngestionResult:
    """
    Write a single ambient interaction event to Stream C.

    STATUS       : stable
    OWNER        : abm.mobile.ambient_manager.AmbientInteractionManager
    DEPENDENCIES : ServiceRegistry.ambient_manager (-> controller + embedder)
    CONSUMERS    : Flutter foreground service (via local HTTP stub)

    Delegates to ``AmbientInteractionManager.ingest_event()``, which runs
    the full retention-aware write path (validate → compress → store →
    housekeeping).  Source must be one of ``PERMITTED_SOURCE_KINDS``:
    ``git_commit``, ``workspace_file``, ``design_doc``.

    Clipboard, voice, and browser sources are not permitted in Phase v1.0
    (PROJECT_BRIEF.md ground rule 8).

    Never raises to the caller.

    Parameters
    ----------
    event : AmbientEvent
        The ambient event to persist.
    registry : ServiceRegistry
        Booted service registry.

    Returns
    -------
    AmbientIngestionResult
    """
    try:
        manager = registry.ambient_manager
        write_result = manager.ingest_event(event)
        return AmbientIngestionResult(
            status=write_result.status,
            doc_id=write_result.doc_id,
            reason=write_result.reason,
            housekeeper_ran=write_result.housekeeper_ran,
            degraded=False,
        )
    except Exception as exc:
        logger.error("ingestAmbientEvent: unexpected error: %s", exc)
        return AmbientIngestionResult(
            status="error",
            reason=str(exc),
            degraded=True,
        )


# ============================================================================
# ── FUTURE CAPABILITIES ──────────────────────────────────────────────────────
# Documented stubs only. No backend exists. See ARCHITECTURE_BACKLOG.md.
# A console command may ONLY be added the day its backend phase is gated.
# ============================================================================


def continueTask(task_id: str, *, registry: ServiceRegistry) -> None:
    """
    Resume a previously interrupted task.

    STATUS       : future
    OWNER        : (not yet designed)
    DEPENDENCIES : session-state / task-continuation engine (does not exist)
    CONSUMERS    : (none — no console command until backend is gated)

    Deferred: requires session-state tracking not yet designed anywhere in
    the roadmap. See ARCHITECTURE_BACKLOG.md and CLIENT_01_CONSOLE.md.
    """
    raise NotImplementedError(
        "continueTask is a FUTURE capability. "
        "Its backend has no phase brief or test gate yet. "
        "See ARCHITECTURE_BACKLOG.md."
    )


def reflectOnWork(*, registry: ServiceRegistry) -> None:
    """
    Trigger a reflection pass over recent work.

    STATUS       : future
    OWNER        : (not yet designed — reflection engine)
    DEPENDENCIES : reflection engine (does not exist in any ABM_SPEC.md phase)
    CONSUMERS    : (none — no console command until backend is gated)

    Deferred: requires a reflection engine. See CLIENT_01_CONSOLE.md.
    """
    raise NotImplementedError(
        "reflectOnWork is a FUTURE capability. "
        "Its backend has no phase brief or test gate yet. "
        "See ARCHITECTURE_BACKLOG.md."
    )


def planProject(project: str, *, registry: ServiceRegistry) -> None:
    """
    Generate a project plan.

    STATUS       : future
    OWNER        : (not yet designed — planning agent)
    DEPENDENCIES : planning agent (does not exist in any ABM_SPEC.md phase)
    CONSUMERS    : (none — no console command until backend is gated)

    Deferred: requires a planning agent. See CLIENT_01_CONSOLE.md.
    """
    raise NotImplementedError(
        "planProject is a FUTURE capability. "
        "Its backend has no phase brief or test gate yet. "
        "See ARCHITECTURE_BACKLOG.md."
    )


def learnTopic(topic: str, *, registry: ServiceRegistry) -> None:
    """
    Autonomously research and learn a topic.

    STATUS       : future
    OWNER        : (not yet designed — autonomous research-task queue)
    DEPENDENCIES : research-task queue (does not exist in any ABM_SPEC.md phase)
    CONSUMERS    : (none — no console command until backend is gated)

    Deferred: requires an autonomous research-task queue. See CLIENT_01_CONSOLE.md.
    """
    raise NotImplementedError(
        "learnTopic is a FUTURE capability. "
        "Its backend has no phase brief or test gate yet. "
        "See ARCHITECTURE_BACKLOG.md."
    )


# ============================================================================
# Public surface
# ============================================================================

__all__ = [
    # Return types
    "AnswerResult",
    "KnowledgeResult",
    "StatusResult",
    "MemoryResult",
    "ExplainResult",
    "AmbientIngestionResult",
    # Stable capabilities
    "answerQuestion",
    "retrieveKnowledge",
    "getSystemStatus",
    "summarizeProject",
    "aggregateProjectMemory",
    "explainAuditRecord",
    "ingestAmbientEvent",
    # Future capabilities (stubs)
    "continueTask",
    "reflectOnWork",
    "planProject",
    "learnTopic",
]
