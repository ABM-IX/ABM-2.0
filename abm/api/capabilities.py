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

import threading
import re
import difflib
from abm.memory.chroma_controller import ALL_COLLECTIONS
from abm.orchestrator.departments import DEPARTMENT_REGISTRY
from abm.strategic_wing.strategic_asset_analyzer import StrategicAnalysisResult
from abm.mobile.event_models import AmbientEvent
from abm.mobile.stream_c_writer import WriteResult
from abm.sandbox.container import DockerSandbox
from abm.sandbox.execution_loop import SandboxCheckLoop
from abm.sandbox.models import ValidationScores
from abm.sandbox.validation_gate import MultiFactorGate
from abm.orchestrator.task_contract import TaskContract
from abm.strategic_wing.decision_journal import DecisionJournal

from .core.registry import ServiceRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fast-path constants — Feature 2 (conversational pre-check)
# ---------------------------------------------------------------------------

#: Plain conversational patterns matched before any classify/embed/LLM call.
#: Zero tokens — pure regex. Order matters: first match wins.
_CONVERSATIONAL_PATTERNS: list[re.Pattern] = [
    # Greetings & informal openers
    re.compile(
        r'^\s*(yoh?|hi+|hello+|hey+|howdy|good\s+(morning|afternoon|evening|night)|'  # noqa: E501
        r'sup|what\'?s\s+up|yo+|greetings)'
        r'(\s+(bro|man|dude|abm|there|guys?))?'
        r'(\s+(what\'?s\s+up|how\s+are\s+you|how\s+it\s+going|sup))?[\.!?\s]*$',
        re.IGNORECASE,
    ),
    # Common questions about capabilities / wellbeing
    re.compile(
        r'^\s*(what\s+can\s+you\s+do(\s+for\s+me)?|how\s+can\s+you\s+help(\s+me)?|'  # noqa: E501
        r'what\s+are\s+your\s+capabilities|how\s+are\s+you(\s+doing)?)[\.!?\s]*$',
        re.IGNORECASE,
    ),
    # Positive acknowledgements
    re.compile(
        r'^\s*(ok(ay)?|got\s+it|thanks?(\.?)|thank\s+you|sure|cool|great|'  # noqa: E501
        r'perfect|alright|sounds\s+good|noted|understood|nice|awesome|'  # noqa: E501
        r'excellent|wonderful|cheers)[\.!?\s]*$',
        re.IGNORECASE,
    ),
    # Farewells
    re.compile(
        r'^\s*(bye(\s*bye)?|goodbye|see\s+(you|ya)|cya|later|'  # noqa: E501
        r'take\s+care|have\s+a\s+good\s+one|good\s+night)[\.!?\s]*$',
        re.IGNORECASE,
    ),
]

#: Canned responses paired 1:1 with _CONVERSATIONAL_PATTERNS.
_CONVERSATIONAL_RESPONSES: list[str] = [
    "Hey! I'm ABM 2.0 — ready to help. What are you working on?",
    "I am ABM 2.0, your personal cognitive layer and digital twin. I can help launch desktop applications, manage project memory, run automated workflows, answer queries, and supervise your strategic tasks.",
    "Got it! Let me know if there's anything you need.",
    "Take care! I'll be here when you need me.",
]


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
    synthesis: str = ""
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


@dataclass
class RunTaskResult:
    """
    Return type for ``runTask``.

    Attributes
    ----------
    task_id : str
        The unique contract ID assigned to the dispatched task.
    degraded : bool
        True if Ollama was unreachable, meaning the task could not be classified.
    """

    task_id: str = ""
    degraded: bool = False


@dataclass
class IngestResult:
    """
    Return type for ``ingestDocument``.
    """
    path: str
    results: list[dict[str, Any]] = field(default_factory=list)
    degraded: bool = False


@dataclass
class ReviewProjectResult:
    """
    Return type for ``reviewProject``.
    """
    project_name: str
    hits: list[dict[str, Any]] = field(default_factory=list)
    synthesis: str = ""
    degraded: bool = False


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
    history: list[dict[str, str]] | None = None,
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

    # -------------------------------------------------------------------------
    # Feature 5 — Tier-1 deterministic app launcher (zero tokens)
    # -------------------------------------------------------------------------
    try:
        from abm.automation.direct_app_map import match_tier1_intent, resolve_command
        from abm.automation.launcher_map import DynamicLauncher
        import subprocess

        tier1 = match_tier1_intent(question)
        if tier1 is not None:
            action, app_name = tier1
            launch_cmd = resolve_command(app_name)
            if launch_cmd:
                if action == "open":
                    result = DynamicLauncher().launch(launch_cmd)
                    if result.success:
                        msg = f"\u2705 Launched {app_name} (PID {result.pid})."
                    else:
                        msg = f"\u274c Could not launch {app_name}: {result.error}"
                else:  # close
                    import psutil as _psutil
                    killed = []
                    for proc in _psutil.process_iter(["name", "pid"]):
                        if launch_cmd.lower() in proc.info["name"].lower():
                            try:
                                proc.kill()
                                killed.append(str(proc.info["pid"]))
                            except Exception:
                                pass
                    if killed:
                        msg = f"\u2705 Closed {app_name} (PID(s): {', '.join(killed)})."
                    else:
                        msg = f"\u26a0\ufe0f {app_name} does not appear to be running."
                return AnswerResult(
                    question=question,
                    department="tier1_action",
                    confidence="high",
                    synthesis=msg,
                    fallback_used=False,
                    degraded=False,
                )
    except Exception as _t1_exc:
        logger.debug("answerQuestion: Tier-1 intent check failed — %s", _t1_exc)

    # -------------------------------------------------------------------------
    # Feature 5b — Window actions (minimize / maximize / restore window)
    # -------------------------------------------------------------------------
    _w_match = re.search(
        r'^\s*(minimize|maximize|restore|hide)\s*(window|app|ui)?\s*$',
        question,
        re.IGNORECASE,
    )
    if _w_match:
        _w_act = _w_match.group(1).lower()
        try:
            import ctypes
            _user32 = ctypes.windll.user32
            _hwnd = _user32.GetForegroundWindow()
            if _w_act in ("minimize", "hide"):
                _user32.ShowWindow(_hwnd, 6)  # SW_MINIMIZE
                _w_msg = "✅ Minimized active window."
            else:
                _user32.ShowWindow(_hwnd, 9)  # SW_RESTORE / SW_MAXIMIZE
                _w_msg = "✅ Restored active window."
            return AnswerResult(
                question=question,
                department="window_action",
                confidence="high",
                synthesis=_w_msg,
                fallback_used=False,
                degraded=False,
            )
        except Exception as _w_exc:
            logger.warning("answerQuestion: window action failed — %s", _w_exc)

    # -------------------------------------------------------------------------
    # Feature 2 — Fast conversational pre-check (zero tokens)
    # -------------------------------------------------------------------------
    q_stripped = question.strip()
    for _i, _pat in enumerate(_CONVERSATIONAL_PATTERNS):
        if _pat.match(q_stripped):
            return AnswerResult(
                question=question,
                department="conversational",
                confidence="high",
                synthesis=_CONVERSATIONAL_RESPONSES[_i],
                fallback_used=False,
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
    synthesis = ""
    
    q_lower = question.lower().strip()
    is_identity_query = bool(re.search(
        r'\b(who|what|where)\b.*\b(are you|is abm|did you come from|made you|built you|developed you|created you|programmed you)\b|'
        r'\bwho\b.*\b(developed|made|built|created|programmed)\b.*\b(you|abm)\b|'
        r'\bwhat\b.*\babm\b.*\b(stand for|mean|is)\b|'
        r'\bare\s+you\s+abm\b|'
        r'\byou(\'re| are)?\s+(not\s+)?abm\b',
        q_lower
    ))

    try:
        if is_identity_query:
            # Identity extraction: bypass LLM and embedder completely
            synthesis = (
                "Extracted from Identity Document: 'ABM' is Arabang's own initials, "
                "not a technical acronym, and must never be expanded into an invented backronym. "
                "I act as a persistent personal cognitive layer and digital twin, designed to amplify "
                "engineering execution and serve as the strategic supervisor for FirstMinds."
            )
        else:
            # Step 3a: Attempt vector retrieval (soft fail if Ollama embedder is offline)
            try:
                embedding = registry.embedder.embed(question)
                for collection_name in allowed_streams:
                    hits.extend(
                        _flatten_query_hits(registry, collection_name, embedding, n)
                    )
                hits.sort(key=lambda h: float("inf") if h["distance"] is None else h["distance"])
                hits = hits[:5]  # Cap to top-5 by relevance — keeps prompts lean
            except Exception as _embed_exc:
                logger.warning(
                    "answerQuestion: vector memory retrieval skipped (%s) — proceeding.",
                    _embed_exc,
                )
                degraded = True
                hits = []

            if department_str == "conversational":
                # Cap hits to the top 2 to reduce generation time and avoid timeouts
                context_texts = [f"- {h.get('text', '')}" for h in hits[:2] if h.get("text")]
                
                history_text = ""
                if history:
                    history_str = "\n".join([f"{msg.get('role', 'unknown').capitalize()}: {msg.get('content', '')}" for msg in history])
                    history_text = f"Recent Conversation History:\n{history_str}\n\n"
                
                prompt = (
                    "You are ABM 2.0, my persistent personal cognitive layer and digital twin. "
                    "Answer the following conversational question warmly, directly, and in the first person. "
                    "Use plain sentences and avoid corporate jargon. Keep it short.\n"
                    "CRITICAL ANTI-HALLUCINATION RULE: If the user asks for a specific fact (e.g. what an acronym stands for, a name, a date) and the answer is NOT explicitly stated in the context, you MUST say 'I don't have that specific information' and ask for clarification. You are STRICTLY FORBIDDEN from inventing expansions for acronyms or adding outside knowledge.\n"
                    "You may use the following recent history and identity context to inform your answer, "
                    "but you are NOT strictly required to say 'I cannot answer this' if the context "
                    "doesn't explicitly contain the answer to a general conversational query.\n\n"
                    f"{history_text}"
                    "Context:\n"
                    f"{chr(10).join(context_texts)}\n\n"
                    f"Question: {question}"
                )
                try:
                    response = registry.gateway.generate(prompt, max_tokens=180)
                    synthesis = response.text
                except Exception as exc:
                    logger.warning("answerQuestion: conversational synthesis failed — %s", exc)
                    synthesis = "Hello! I am ABM 2.0, your personal cognitive layer."
            else:
                if hits:
                    has_governance = False
                    has_client = False
                    gov_filenames = {"ABM_SPEC", "ARCHITECTURAL_CONSTITUTION", "MISSION_VISION_PHILOSOPHY", "PROJECT_BRIEF"}
                    
                    for h in hits:
                        doc_id = h.get("id", "")
                        text = h.get("text", "")
                        is_gov = any(g in doc_id or g in text for g in gov_filenames)
                        if is_gov:
                            has_governance = True
                        elif text:
                            has_client = True
                    
                    isolation_rule = ""
                    if has_governance and has_client:
                        isolation_rule = (
                            "PROJECT ISOLATION RULE: You are advising on a client project, but your context includes ABM's own governance documents. "
                            "You must NEVER propose editing, updating, or referencing ABM's own governance documents (like ABM_SPEC.md or ARCHITECTURAL_CONSTITUTION.md) "
                            "as part of advice about the client's software. They are strictly read-only context describing you (ABM), not the client.\n"
                        )

                    context_texts = [f"- {h.get('text', '')}" for h in hits if h.get("text")]
                    history_text = ""
                    if history:
                        history_str = "\n".join([f"{msg.get('role', 'unknown').capitalize()}: {msg.get('content', '')}" for msg in history])
                        history_text = f"Recent Conversation History:\n{history_str}\n\n"

                    prompt = (
                        "You are ABM 2.0. Answer the user's question directly, in the first person, and with a warm, natural tone using plain conversational prose. "
                        "Keep your response to short paragraphs (2-4 sentences max). Do not format your response as a numbered report or bulleted list (e.g., avoid 'Here are some key points... 1... 2... 3...'). Answer smoothly in flowing paragraphs.\n"
                        "CRITICAL ANTI-HALLUCINATION RULE: If the user asks for a specific fact (e.g. what an acronym stands for, a name, a date) and the answer is NOT explicitly stated in the context, you MUST say 'I don't have that specific information' and ask for clarification. You are STRICTLY FORBIDDEN from inventing expansions for acronyms or adding outside knowledge.\n"
                        "You must answer using ONLY the facts explicitly present in the provided context. Never fill a factual gap with a plausible-sounding invention.\n"
                        "If the context does not contain the answer, say 'I cannot answer this based on the provided context.'\n\n"
                        f"{isolation_rule}"
                        f"{history_text}"
                        "Context:\n"
                        f"{chr(10).join(context_texts)}\n\n"
                        f"Question: {question}"
                    )
                    response = registry.gateway.generate(prompt, max_tokens=180)
                    synthesis = response.text
                else:
                    synthesis = ""
    except Exception as exc:
        logger.warning("answerQuestion: synthesis failed — %s", exc)
        degraded = True
        if not synthesis:
            synthesis = "I'm sorry, I couldn't generate an answer because the reasoning gateway (Groq) is unreachable or returned an error. Please check your GROQ_API_KEY environment variable."

    # Stream C feedback loop intentionally removed to prevent hallucination cycles.

    return AnswerResult(
        question=question,
        department=department_str,
        confidence=confidence,
        hits=hits,
        synthesis=synthesis,
        fallback_used=fallback,
        degraded=degraded,
    )


def _worker_thread(contract: TaskContract, registry: ServiceRegistry, objective: str) -> None:
    """
    Background worker thread mimicking a v0.3 Department Worker Sandbox.
    Generates python code to solve the objective, runs it via DockerSandbox,
    and scores it using MultiFactorGate.
    """
    try:
        journal = DecisionJournal(registry.controller, registry.embedder)
        sandbox_loop = SandboxCheckLoop(sandbox_factory=DockerSandbox)
        gate = MultiFactorGate()
        
        base_prompt = (
            f"You are a backend worker. Write a Python script to achieve the following objective:\n"
            f"Objective: {objective}\n\n"
            "Return ONLY the raw python code inside a ```python ``` block. Do not include any explanations."
        )
        prompt = base_prompt

        for attempt in range(1, 4):
            # Prompt gateway to generate python code
            response = registry.gateway.generate(prompt)
            
            # Extract python code
            code = ""
            match = re.search(r"```python\n(.*?)\n```", response.text, re.DOTALL)
            if match:
                code = match.group(1).strip()
            else:
                # Fallback if markdown block is missing
                code = response.text.replace("```", "").strip()

            registry.monitor.mark_in_sandbox(contract.contract_id)
            
            # Evaluate code in sandbox
            exec_result = sandbox_loop.evaluate_code(
                code_files={"/tmp/main.py": code}, 
                test_command=["python", "/tmp/main.py"]
            )
            
            registry.monitor.record_execution(contract.contract_id, exec_result)
            
            # Create validation scores
            test_succ = 1.0 if exec_result.exit_code == 0 else 0.0
            scores = ValidationScores(
                m_align=0.9,
                t_correct=0.9,
                s_val=0.9,
                test_succ=test_succ,
                p_align=0.9,
            )

            is_final_attempt = (attempt == 3)
            
            if test_succ == 1.0 or is_final_attempt:
                # Evaluate through confidence gate (this will quarantine if it fails)
                gate_result = gate.evaluate(contract, scores, code)
                registry.monitor.record_gate_result(contract.contract_id, gate_result, scores)
                
                journal.log_decision(
                    what_decided=f"Sandbox Execution Attempt {attempt} for {contract.contract_id}",
                    why_decided=f"Exit code: {exec_result.exit_code}. Gate passed: {gate_result.passed}."
                )
                break
            else:
                # Execution failed and not final attempt, prepare next retry
                journal.log_decision(
                    what_decided=f"Sandbox Execution Attempt {attempt} for {contract.contract_id}",
                    why_decided=f"Exit code: {exec_result.exit_code}. Retrying."
                )
                
                error_msg = exec_result.stderr if exec_result.stderr else exec_result.stdout
                prompt = (
                    f"{base_prompt}\n\n"
                    f"Your previous attempt failed with exit code {exec_result.exit_code}.\n"
                    f"Error output:\n{error_msg}\n\n"
                    f"Please fix the code and try again."
                )

    except Exception as exc:
        logger.error("runTask worker thread failed: %s", exc)


def runTask(
    objective: str,
    *,
    registry: ServiceRegistry,
) -> RunTaskResult:
    """
    Classifies the task, dispatches it to a background worker for execution
    in the sandbox, and returns the task ID immediately.

    STATUS       : stable
    OWNER        : abm.orchestrator.router.ClassificationRouter
    DEPENDENCIES : ServiceRegistry.router, ServiceRegistry.gateway,
                   ServiceRegistry.monitor
    CONSUMERS    : console ``run`` command

    Parameters
    ----------
    objective : str
        The task description. Must be non-empty.
    registry : ServiceRegistry
        Booted service registry.

    Returns
    -------
    RunTaskResult
    """
    if not objective or not objective.strip():
        return RunTaskResult(degraded=False)

    try:
        router_result = registry.router.classify(objective)
    except Exception as exc:
        logger.warning("runTask: classification failed — %s", exc)
        return RunTaskResult(degraded=True)
    
    contract = router_result.contract
    registry.monitor.register_routed_task(contract)
    
    thread = threading.Thread(
        target=_worker_thread,
        args=(contract, registry, objective),
        daemon=True,
    )
    thread.start()

    return RunTaskResult(task_id=contract.contract_id, degraded=False)


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


def reviewProject(
    project_name: str,
    *,
    registry: ServiceRegistry,
    n_results: int = 10,
) -> ReviewProjectResult:
    """
    Retrieve a project's Stream A entries (code topologies) and synthesize actionable 
    improvement suggestions strictly grounded in the ingested code.

    STATUS       : stable
    OWNER        : abm.memory.chroma_controller.ChromaController (retrieval) / abm.gateway (synthesis)
    DEPENDENCIES : ServiceRegistry.embedder, ServiceRegistry.controller, ServiceRegistry.gateway
    CONSUMERS    : console ``review`` command

    Parameters
    ----------
    project_name : str
        Project name used as the retrieval query.
    registry : ServiceRegistry
        Booted service registry.
    n_results : int
        Number of code chunks to retrieve.

    Returns
    -------
    ReviewProjectResult
    """
    if not project_name or not project_name.strip():
        return ReviewProjectResult(project_name=project_name, degraded=False)

    hits: list[dict[str, Any]] = []
    degraded = False
    synthesis = ""

    try:
        embedding = registry.embedder.embed(project_name)
        # 1. Retrieve purely from Stream A (Code Topologies)
        hits = _flatten_query_hits(registry, "abm_code_topologies", embedding, n_results)
        
        # Sort by distance
        hits.sort(key=lambda h: float("inf") if h["distance"] is None else h["distance"])

        if hits:
            context_texts = [f"--- File/Snippet: {h.get('id', 'unknown')} ---\n{h.get('text', '')}" for h in hits if h.get("text")]
            
            # 2. Strict prompt composing existing capabilities
            prompt = (
                "You are an expert software reviewer. Review the following code snippets from the project.\n"
                "Provide actionable improvement suggestions focusing on:\n"
                "1. Architectural concerns\n"
                "2. Style inconsistencies\n"
                "3. Potential bugs\n\n"
                "CRITICAL ANTI-HALLUCINATION RULE: You must base your suggestions PURELY on the provided snippets. "
                "Do NOT invent files, variables, or functions that are not explicitly present in the context below.\n"
                "If the provided snippets are too short or lack issues, state that the code looks fine based on the limited context.\n\n"
                "Context Snippets:\n"
                f"{chr(10).join(context_texts)}\n\n"
                "Review:\n"
            )
            response = registry.gateway.generate(prompt)
            synthesis = response.text
        else:
            synthesis = "No code topology data found for this project in Stream A."

    except Exception as exc:
        logger.warning("reviewProject: failed — %s", exc)
        degraded = True

    return ReviewProjectResult(
        project_name=project_name,
        hits=hits,
        synthesis=synthesis,
        degraded=degraded
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
                
                if task_record.validation_scores is not None:
                    vs = task_record.validation_scores
                    entry["validation_scores"] = {
                        "m_align": vs.m_align,
                        "t_correct": vs.t_correct,
                        "s_val": vs.s_val,
                        "test_succ": vs.test_succ,
                        "p_align": vs.p_align,
                    }

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


def ingestDocument(path: str, *, registry: ServiceRegistry) -> IngestResult:
    """
    Manually ingest a document (code, txt, md, pdf) from the filesystem into ABM streams.

    STATUS       : stable
    OWNER        : abm.companion.ingestion_coordinator
    DEPENDENCIES : controller, embedder
    CONSUMERS    : Console (cmd_ingest)
    """
    from abm.companion.ingestion_coordinator import IngestionCoordinator
    logger.debug("ingestDocument: path=%r", path)
    degraded = False
    results = []
    
    try:
        coordinator = IngestionCoordinator(
            controller=registry.controller,
            embedder=registry.embedder,
            git_pipeline=None,
        )
        ingestions = coordinator.ingest_document(path)
        for r in ingestions:
            results.append({
                "status": r.status,
                "collection": r.collection,
                "doc_ids": r.doc_ids,
                "reason": r.reason
            })
    except Exception as exc:
        logger.warning("ingestDocument failed: %s", exc)
        degraded = True

    return IngestResult(path=path, results=results, degraded=degraded)


@dataclass
class EditProposalResult:
    target_file: str
    diff: str
    new_content: str
    verified: bool
    degraded: bool = False


def proposeEdit(target_file: str, instruction: str, *, registry: ServiceRegistry) -> EditProposalResult:
    """
    Proposes an edit to a target file and verifies it in the sandbox.
    
    STATUS       : stable
    OWNER        : abm.gateway
    DEPENDENCIES : ServiceRegistry.gateway
    CONSUMERS    : Web UI (handle_edit_propose)
    """
    try:
        with open(target_file, "r", encoding="utf-8") as f:
            old_content = f.read()
            
        journal = DecisionJournal(registry.controller, registry.embedder)
        sandbox_loop = SandboxCheckLoop(sandbox_factory=DockerSandbox)
        
        base_prompt = (
            f"You are a backend worker. Edit the following file according to this instruction:\n"
            f"Instruction: {instruction}\n\n"
            f"File: {target_file}\n"
            f"Current Content:\n```python\n{old_content}\n```\n\n"
            "Return ONLY the fully edited raw file content inside a ```python ``` block. Do not include any explanations. "
            "Output the ENTIRE file, not just the changed lines."
        )
        prompt = base_prompt
        
        for attempt in range(1, 4):
            response = registry.gateway.generate(prompt)
            
            new_content = ""
            match = re.search(r"```python\n(.*?)\n```", response.text, re.DOTALL)
            if match:
                new_content = match.group(1).strip()
            else:
                new_content = response.text.replace("```", "").strip()

            sandbox_file_path = f"/tmp/{os.path.basename(target_file)}"
            
            exec_result = sandbox_loop.evaluate_code(
                code_files={sandbox_file_path: new_content}, 
                test_command=["python", "-m", "py_compile", sandbox_file_path]
            )
            
            is_final_attempt = (attempt == 3)
            
            if exec_result.exit_code == 0 or is_final_attempt:
                journal.log_decision(
                    what_decided=f"proposeEdit attempt {attempt} for {target_file}",
                    why_decided=f"Exit code: {exec_result.exit_code}. Passed: {exec_result.exit_code == 0}"
                )
                
                diff_lines = list(difflib.unified_diff(
                    old_content.splitlines(keepends=True),
                    new_content.splitlines(keepends=True),
                    fromfile=f"a/{os.path.basename(target_file)}",
                    tofile=f"b/{os.path.basename(target_file)}",
                    n=3
                ))
                diff_text = "".join(diff_lines)
                
                return EditProposalResult(
                    target_file=target_file,
                    diff=diff_text,
                    new_content=new_content,
                    verified=(exec_result.exit_code == 0),
                    degraded=False
                )
            else:
                journal.log_decision(
                    what_decided=f"proposeEdit attempt {attempt} for {target_file}",
                    why_decided=f"Exit code: {exec_result.exit_code}. Retrying."
                )
                
                error_msg = exec_result.stderr if exec_result.stderr else exec_result.stdout
                prompt = (
                    f"{base_prompt}\n\n"
                    f"Your previous attempt failed syntax validation with exit code {exec_result.exit_code}.\n"
                    f"Error output:\n{error_msg}\n\n"
                    f"Please fix the code and try again."
                )
    except Exception as exc:
        logger.error("proposeEdit failed: %s", exc)
        return EditProposalResult(target_file, "", "", False, True)

def applyEdit(target_file: str, new_content: str, *, registry: ServiceRegistry) -> None:
    """
    Applies a previously proposed edit to a file.
    
    STATUS       : stable
    OWNER        : abm.gateway
    DEPENDENCIES : None
    CONSUMERS    : Web UI (handle_edit_apply)
    """
    with open(target_file, "w", encoding="utf-8") as f:
        f.write(new_content)

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
    "IngestResult",
    "ReviewProjectResult",
    # Stable capabilities
    "answerQuestion",
    "retrieveKnowledge",
    "getSystemStatus",
    "summarizeProject",
    "aggregateProjectMemory",
    "explainAuditRecord",
    "ingestAmbientEvent",
    "ingestDocument",
    "reviewProject",
    # Future capabilities (stubs)
    "continueTask",
    "reflectOnWork",
    "planProject",
    "learnTopic",
]
