"""
abm/orchestrator/router.py
============================
Classification Router — Phase v0.3 Executive Orchestrator Engine
Spec Reference: ABM_SPEC.md sections 4, 5, and 10 (item 3)

The non-generating classification router node. Given an incoming task
description, it classifies which department/domain it belongs to and
returns a RouterResult containing a fully-formed TaskContract.

THE FUNDAMENTAL CONSTRAINT (spec section 5):
  This class is programmatically banned from generating any raw code
  or text explanations. It does NOT have generate(), write(), respond(),
  explain(), or complete() methods. Its only public output is a
  RouterResult — a structured routing decision.

Architecture:
  ClassificationRouter
    │
    ├── OllamaModelGateway  ← calls phi3:mini for classification
    │     (no text generation — only a JSON-shaped prompt)
    │
    ├── ChromaController    ← optional Stream D context injection
    │     (read-only, never writes during classification)
    │
    ├── DEPARTMENT_REGISTRY ← looks up sandbox config
    │
    └── TaskContract.build() ← assembles the delegation contract

Design contract:
  - classify() is the ONLY public action method.
  - is_available() is the ONLY other public method — it checks Ollama health.
  - Fallback policy: any failure (Ollama down, bad JSON, unknown department)
    returns department=software_engineering with confidence_hint="low" and
    fallback_used=True. The router NEVER raises to its caller.
  - Stream D context injection: if controller and embedder are provided,
    the router performs a top-1 semantic query against abm_cognitive_identity
    before building the prompt. This grounds the classification in ABM's
    actual strategic priorities. Gracefully skipped on any error.
  - The prompt instructs phi3:mini to return ONLY a JSON object:
    {"department": "<value>", "confidence": "<high|medium|low>"}
    Any extra prose is stripped during JSON extraction.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from abm.api.core.interfaces import (
    EmbedderInterface,
    ModelGatewayInterface,
    VectorStoreInterface,
)
from abm.memory.chroma_controller import COLLECTION_COGNITIVE_IDENTITY

from .departments import (
    Department,
    DepartmentWorkerSandbox,
    department_from_string,
    get_sandbox,
)
from .model_gateway import ModelGatewayError
from .task_contract import RouterResult, TaskContract

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Default department when classification fails or is ambiguous.
FALLBACK_DEPARTMENT: Department = Department.SOFTWARE_ENGINEERING

#: Maximum characters of task description sent to phi3:mini.
MAX_TASK_DESCRIPTION_CHARS: int = 2000

#: Valid confidence hint values.
CONFIDENCE_HINTS: frozenset[str] = frozenset({"high", "medium", "low"})

#: Regex to extract the first JSON object from free-form model output.
_JSON_OBJECT_RE: re.Pattern[str] = re.compile(r"\{[^{}]+\}", re.DOTALL)

#: Classification prompt template. Filled in by _build_prompt().
_CLASSIFICATION_PROMPT_TEMPLATE: str = """\
You are a task classification system. You must classify the following task
into exactly one department from this list:

  - software_engineering  : code, bugs, features, refactoring, tests
  - strategic_planning    : goals, OKRs, business decisions, roadmaps
  - architecture          : system design, dependencies, technical trade-offs
  - security              : vulnerabilities, secrets, compliance, scanning
  - memory_indexing       : ingestion, re-indexing, database maintenance

{context_block}

TASK:
{task_description}

Respond with ONLY the following JSON object and nothing else:
{{"department": "<department_value>", "confidence": "<high|medium|low>"}}
"""

_CONTEXT_BLOCK_TEMPLATE: str = """\
CORPORATE IDENTITY CONTEXT (use this to align classification with priorities):
{identity_text}
"""


# ---------------------------------------------------------------------------
# ClassificationRouter
# ---------------------------------------------------------------------------


class ClassificationRouter:
    """
    The non-generating classification router node.

    Accepts a task description string, classifies it into a department using
    phi3:mini via the local Ollama loopback, and returns a ``RouterResult``
    containing a ``TaskContract``.

    **This class does not generate text, code, or explanations.**
    The only public action method is ``classify()``.

    Parameters
    ----------
    gateway : ModelGatewayInterface
        The model gateway used to call phi3:mini. Must be pre-configured
        with the correct model and loopback address.
    controller : VectorStoreInterface | None
        Optional ChromaDB controller for Stream D context injection.
        If ``None``, context injection is skipped.
    embedder : EmbedderInterface | None
        Optional embedding wrapper needed for the Stream D query.
        Required if ``controller`` is provided; ignored if ``controller`` is ``None``.
    """

    def __init__(
        self,
        gateway: ModelGatewayInterface,
        controller: VectorStoreInterface | None = None,
        embedder: EmbedderInterface | None = None,
    ) -> None:
        self._gateway = gateway
        self._controller = controller
        self._embedder = embedder
        logger.info(
            "ClassificationRouter: initialised (model=%s, stream_d_context=%s).",
            gateway.model,
            controller is not None,
        )

    # ------------------------------------------------------------------
    # Public API — classify() and is_available() ONLY
    # ------------------------------------------------------------------

    def classify(self, task_description: str) -> RouterResult:
        """
        Classify a task description into a department and return a routing result.

        This method:
          1. Validates the task description.
          2. Optionally fetches Stream D context for prompt grounding.
          3. Builds a classification-only prompt for phi3:mini.
          4. Calls the gateway and parses the JSON response.
          5. Assembles a ``TaskContract`` from the department registry.
          6. Returns a ``RouterResult``.

        The router never raises. Any failure produces a fallback result
        with ``department=software_engineering`` and ``fallback_used=True``.

        Parameters
        ----------
        task_description : str
            The incoming task to classify. Must be non-empty.

        Returns
        -------
        RouterResult
            The routing decision and delegation contract. Never ``None``.
        """
        t0 = time.monotonic()

        if not task_description or not task_description.strip():
            logger.warning("ClassificationRouter.classify: empty task_description — using fallback.")
            return self._fallback_result(
                task_description="(empty)",
                reason="Task description was empty or whitespace-only.",
                latency_ms=0,
            )

        # Truncate very long descriptions to keep the prompt manageable
        truncated = task_description.strip()[:MAX_TASK_DESCRIPTION_CHARS]

        # Step 1: Optional Stream D context injection
        context_block = self._fetch_stream_d_context(truncated)

        # Step 2: Build classification prompt
        prompt = self._build_prompt(truncated, context_block)

        # Step 3: Call phi3:mini
        try:
            generation = self._gateway.generate(prompt)
            raw_text = generation.text
            model_name = generation.model
        except ModelGatewayError as exc:
            logger.warning(
                "ClassificationRouter.classify: gateway error — %s. Using fallback.", exc
            )
            latency_ms = int((time.monotonic() - t0) * 1000)
            return self._fallback_result(
                task_description=truncated,
                reason=str(exc),
                latency_ms=latency_ms,
                model_name=self._gateway.model,
            )

        # Step 4: Parse JSON classification from model output
        department, confidence, parse_fallback = self._parse_classification(raw_text)

        # Step 5: Look up sandbox and build contract
        sandbox = get_sandbox(department)
        contract = TaskContract.build(
            objective=task_description.strip(),
            department=department,
            assigned_agents=list(sandbox.assigned_agents),
            autonomy_permission_level=sandbox.autonomy_level,
            hard_success_conditions=list(sandbox.hard_success_conditions),
        )

        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "ClassificationRouter.classify: '%s' → '%s' (confidence=%s, fallback=%s, latency=%dms).",
            truncated[:60], department.value, confidence, parse_fallback, latency_ms,
        )

        return RouterResult(
            contract=contract,
            raw_classification=self._extract_department_string(raw_text),
            confidence_hint=confidence,
            model_used=model_name,
            routing_latency_ms=latency_ms,
            fallback_used=parse_fallback,
        )

    def is_available(self) -> bool:
        """
        Check whether the underlying model gateway is reachable.

        Returns ``True`` if the local Ollama server responded to a health
        check. Never raises.

        Returns
        -------
        bool
        """
        return self._gateway.is_available()

    # ------------------------------------------------------------------
    # Internal helpers — none of these generate content
    # ------------------------------------------------------------------

    def _fetch_stream_d_context(self, task_description: str) -> str:
        """
        Query Stream D (abm_cognitive_identity) for the most relevant
        identity/corporate context document.

        Returns a formatted context block string, or ``""`` if no controller
        is configured or the query fails.
        """
        if self._controller is None or self._embedder is None:
            return ""

        try:
            embedding = self._embedder.embed(task_description)
            results = self._controller.query_collection(
                COLLECTION_COGNITIVE_IDENTITY,
                query_embedding=embedding,
                n_results=1,
            )
            documents = results.get("documents", [[]])
            if documents and documents[0]:
                identity_text = documents[0][0][:500]  # Trim to keep prompt lean
                return _CONTEXT_BLOCK_TEMPLATE.format(identity_text=identity_text)
        except Exception as exc:
            logger.debug(
                "ClassificationRouter._fetch_stream_d_context: skipped — %s", exc
            )
        return ""

    @staticmethod
    def _build_prompt(task_description: str, context_block: str) -> str:
        """Build the classification-only prompt for phi3:mini."""
        return _CLASSIFICATION_PROMPT_TEMPLATE.format(
            context_block=context_block,
            task_description=task_description,
        )

    @staticmethod
    def _extract_department_string(raw_text: str) -> str:
        """
        Extract the raw department string from model output for logging.
        Returns ``""`` if no JSON-shaped content is found.
        """
        match = _JSON_OBJECT_RE.search(raw_text)
        if not match:
            return ""
        try:
            data = json.loads(match.group())
            return str(data.get("department", ""))
        except json.JSONDecodeError:
            return ""

    @staticmethod
    def _parse_classification(raw_text: str) -> tuple[Department, str, bool]:
        """
        Parse the phi3:mini response into (Department, confidence_hint, fallback_used).

        Extracts the first JSON object from the raw text (stripping any prose
        the model may have added despite the prompt constraint), then maps the
        ``department`` field to a ``Department`` enum member.

        Returns a third element ``fallback_used=True`` whenever the parser
        had to fall back (no JSON found, JSON decode error, unknown department).
        Falls back to ``(FALLBACK_DEPARTMENT, "low", True)`` on any parse failure.
        """
        match = _JSON_OBJECT_RE.search(raw_text)
        if not match:
            logger.debug(
                "ClassificationRouter._parse_classification: no JSON object found in '%s'.",
                raw_text[:200],
            )
            return FALLBACK_DEPARTMENT, "low", True

        try:
            data: dict[str, Any] = json.loads(match.group())
        except json.JSONDecodeError:
            logger.debug(
                "ClassificationRouter._parse_classification: JSONDecodeError on '%s'.",
                match.group()[:200],
            )
            return FALLBACK_DEPARTMENT, "low", True

        raw_dept = str(data.get("department", "")).strip()
        raw_conf = str(data.get("confidence", "low")).strip().lower()

        # Validate and normalise department
        try:
            department = department_from_string(raw_dept)
        except ValueError:
            logger.debug(
                "ClassificationRouter._parse_classification: unknown department '%s' — fallback.",
                raw_dept,
            )
            return FALLBACK_DEPARTMENT, "low", True

        # Validate confidence hint
        confidence = raw_conf if raw_conf in CONFIDENCE_HINTS else "low"

        return department, confidence, False

    def _fallback_result(
        self,
        task_description: str,
        reason: str,
        latency_ms: int,
        model_name: str | None = None,
    ) -> RouterResult:
        """
        Build a fallback RouterResult when classification cannot be completed.

        Always routes to ``FALLBACK_DEPARTMENT`` (software_engineering) with
        ``confidence_hint="low"`` and ``fallback_used=True``.
        """
        sandbox = get_sandbox(FALLBACK_DEPARTMENT)
        contract = TaskContract.build(
            objective=task_description,
            department=FALLBACK_DEPARTMENT,
            assigned_agents=list(sandbox.assigned_agents),
            autonomy_permission_level=sandbox.autonomy_level,
            hard_success_conditions=list(sandbox.hard_success_conditions),
        )
        logger.info(
            "ClassificationRouter: fallback result issued (reason='%s').", reason
        )
        return RouterResult(
            contract=contract,
            raw_classification="",
            confidence_hint="low",
            model_used=model_name or self._gateway.model,
            routing_latency_ms=latency_ms,
            fallback_used=True,
        )


__all__ = [
    "ClassificationRouter",
    "FALLBACK_DEPARTMENT",
    "MAX_TASK_DESCRIPTION_CHARS",
    "CONFIDENCE_HINTS",
]
