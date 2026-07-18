"""
abm/orchestrator/departments.py
================================
Department Registry — Phase v0.3 Executive Orchestrator Engine
Spec Reference: ABM_SPEC.md sections 4, 5, and 7

Defines the canonical set of departments that the ClassificationRouter can
route tasks to. Each department has a frozen DepartmentWorkerSandbox that
specifies its allowed memory streams, autonomy level, and assigned agents.

This module is a pure data definition. It contains no I/O, no Ollama calls,
and no ChromaDB access. It is the single source of truth for department
configuration — any module that needs to look up a department must import
from here.

Design contract:
  - Department is a str Enum so its values serialise directly into TaskContract
    JSON without an extra conversion step.
  - DepartmentWorkerSandbox is frozen (immutable). Departments cannot be
    reconfigured at runtime.
  - allowed_streams is a frozenset of collection name strings matching the
    four v0.1 collection constants exactly.
  - autonomy_level maps to the five-ring security model in spec section 7.
  - DEPARTMENT_REGISTRY is the single global lookup table. The router and
    contract builder both import from here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from abm.memory.chroma_controller import (
    COLLECTION_AMBIENT_TELEMETRY,
    COLLECTION_CODE_TOPOLOGIES,
    COLLECTION_COGNITIVE_IDENTITY,
    COLLECTION_TECHNICAL_MASTERY,
)


# ---------------------------------------------------------------------------
# Worker tool constants
# ---------------------------------------------------------------------------

TOOL_CHROMA_QUERY = "chroma_query"
TOOL_CODE_STRUCTURE_ANALYZER = "code_structure_analyzer"
TOOL_STYLE_FINGERPRINT_EXTRACTOR = "style_fingerprint_extractor"
TOOL_GIT_PIPELINE = "git_pipeline"
TOOL_FILE_WATCHER = "file_watcher"
TOOL_INGESTION_COORDINATOR = "ingestion_coordinator"
TOOL_MODEL_GATEWAY = "model_gateway"
TOOL_SECURITY_STATIC_SCAN = "security_static_scan"
TOOL_PATCH_PROPOSAL_WRITER = "patch_proposal_writer"
TOOL_STRATEGIC_SUMMARY_BUILDER = "strategic_summary_builder"

ALL_WORKER_TOOLS: frozenset[str] = frozenset(
    {
        TOOL_CHROMA_QUERY,
        TOOL_CODE_STRUCTURE_ANALYZER,
        TOOL_STYLE_FINGERPRINT_EXTRACTOR,
        TOOL_GIT_PIPELINE,
        TOOL_FILE_WATCHER,
        TOOL_INGESTION_COORDINATOR,
        TOOL_MODEL_GATEWAY,
        TOOL_SECURITY_STATIC_SCAN,
        TOOL_PATCH_PROPOSAL_WRITER,
        TOOL_STRATEGIC_SUMMARY_BUILDER,
    }
)


# ---------------------------------------------------------------------------
# Department enum
# ---------------------------------------------------------------------------


class Department(str, Enum):
    """
    Canonical departments the ClassificationRouter can route tasks to.

    Values are lowercase strings that map directly to the ``department``
    field in a ``TaskContract`` (see spec section 5).
    """

    SOFTWARE_ENGINEERING = "software_engineering"
    STRATEGIC_PLANNING   = "strategic_planning"
    ARCHITECTURE         = "architecture"
    SECURITY             = "security"
    MEMORY_INDEXING      = "memory_indexing"


# ---------------------------------------------------------------------------
# DepartmentWorkerSandbox
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DepartmentWorkerSandbox:
    """
    Immutable configuration for a single department worker sandbox.

    This is the data-contract definition of a sandbox (spec section 10,
    item 3). The actual execution context (Docker container) is a Phase v0.4
    concern — this class defines the *rules* each sandbox must operate under.

    Attributes
    ----------
    department : Department
        The department this sandbox belongs to.
    allowed_streams : frozenset[str]
        ChromaDB collection names this sandbox may read from or write to.
        Must be a subset of the four v0.1 collection constants.
    allowed_tools : frozenset[str]
        Tool identifiers this sandbox may call. Must be a subset of
        ``ALL_WORKER_TOOLS``.
    execution_context_id : str
        Stable isolated context identifier for this department worker.
    autonomy_level : int
        Permission level (0–4) per spec section 7:
          0 = Observe Only
          1 = Suggestive Proposals
          2 = Sandbox Simulation
          3 = Controlled Modification
          4 = Autonomous Operation
    assigned_agents : tuple[str, ...]
        Ordered tuple of agent identifiers assigned to this sandbox.
        Matches the ``assigned_agents`` field in ``TaskContract``.
    hard_success_conditions : tuple[str, ...]
        Default success conditions for tasks routed to this department.
        Injected verbatim into ``TaskContract.hard_success_conditions``.
    description : str
        Human-readable description of the department's scope.
    """

    department: Department
    allowed_streams: frozenset[str]
    allowed_tools: frozenset[str]
    execution_context_id: str
    autonomy_level: int
    assigned_agents: tuple[str, ...]
    hard_success_conditions: tuple[str, ...]
    description: str

    def can_access_stream(self, collection_name: str) -> bool:
        """Return True when ``collection_name`` is in this sandbox scope."""
        return collection_name in self.allowed_streams

    def can_use_tool(self, tool_name: str) -> bool:
        """Return True when ``tool_name`` is in this sandbox tool scope."""
        return tool_name in self.allowed_tools


# ---------------------------------------------------------------------------
# Department registry
# ---------------------------------------------------------------------------

#: All valid ChromaDB collection names — used to validate allowed_streams.
_ALL_STREAMS: frozenset[str] = frozenset(
    {
        COLLECTION_COGNITIVE_IDENTITY,
        COLLECTION_CODE_TOPOLOGIES,
        COLLECTION_TECHNICAL_MASTERY,
        COLLECTION_AMBIENT_TELEMETRY,
    }
)


def _sandbox(
    department: Department,
    streams: frozenset[str],
    tools: frozenset[str],
    autonomy_level: int,
    agents: tuple[str, ...],
    success_conditions: tuple[str, ...],
    description: str,
) -> DepartmentWorkerSandbox:
    """Validate and construct a DepartmentWorkerSandbox."""
    invalid = streams - _ALL_STREAMS
    if invalid:
        raise ValueError(
            f"DepartmentWorkerSandbox for {department.value}: "
            f"allowed_streams contains unknown collection(s): {invalid}"
        )
    invalid_tools = tools - ALL_WORKER_TOOLS
    if invalid_tools:
        raise ValueError(
            f"DepartmentWorkerSandbox for {department.value}: "
            f"allowed_tools contains unknown tool(s): {invalid_tools}"
        )
    if not 0 <= autonomy_level <= 4:
        raise ValueError(
            f"DepartmentWorkerSandbox for {department.value}: "
            f"autonomy_level must be 0–4, got {autonomy_level}"
        )
    if not agents:
        raise ValueError(
            f"DepartmentWorkerSandbox for {department.value}: "
            f"assigned_agents must not be empty."
        )
    return DepartmentWorkerSandbox(
        department=department,
        allowed_streams=streams,
        allowed_tools=tools,
        execution_context_id=f"sandbox:{department.value}",
        autonomy_level=autonomy_level,
        assigned_agents=agents,
        hard_success_conditions=success_conditions,
        description=description,
    )


#: Canonical department → sandbox configuration.
#: The ClassificationRouter and TaskContract builder both use this registry.
DEPARTMENT_REGISTRY: dict[Department, DepartmentWorkerSandbox] = {
    Department.SOFTWARE_ENGINEERING: _sandbox(
        department=Department.SOFTWARE_ENGINEERING,
        streams=frozenset(
            {
                COLLECTION_CODE_TOPOLOGIES,
                COLLECTION_TECHNICAL_MASTERY,
                COLLECTION_AMBIENT_TELEMETRY,
            }
        ),
        tools=frozenset(
            {
                TOOL_CHROMA_QUERY,
                TOOL_CODE_STRUCTURE_ANALYZER,
                TOOL_STYLE_FINGERPRINT_EXTRACTOR,
                TOOL_GIT_PIPELINE,
                TOOL_PATCH_PROPOSAL_WRITER,
            }
        ),
        autonomy_level=2,
        agents=("architecture_node", "code_specialist"),
        success_conditions=(
            "syntax_tree_validity == true",
            "security_vulnerability_scan == clean",
            "unit_test_compilation == success",
        ),
        description=(
            "Handles code synthesis, refactoring, bug fixing, and feature "
            "implementation tasks. Scoped to Streams A, B, and C."
        ),
    ),
    Department.STRATEGIC_PLANNING: _sandbox(
        department=Department.STRATEGIC_PLANNING,
        streams=frozenset(
            {
                COLLECTION_COGNITIVE_IDENTITY,
                COLLECTION_TECHNICAL_MASTERY,
            }
        ),
        tools=frozenset(
            {
                TOOL_CHROMA_QUERY,
                TOOL_MODEL_GATEWAY,
                TOOL_STRATEGIC_SUMMARY_BUILDER,
            }
        ),
        autonomy_level=1,
        agents=("planning_engine",),
        success_conditions=(
            "strategic_alignment_with_stream_d == true",
            "proposal_document_generated == true",
        ),
        description=(
            "Handles high-level planning, resource analysis, and corporate "
            "strategic decisions. Scoped to Streams D and B."
        ),
    ),
    Department.ARCHITECTURE: _sandbox(
        department=Department.ARCHITECTURE,
        streams=frozenset(
            {
                COLLECTION_CODE_TOPOLOGIES,
                COLLECTION_COGNITIVE_IDENTITY,
                COLLECTION_TECHNICAL_MASTERY,
            }
        ),
        tools=frozenset(
            {
                TOOL_CHROMA_QUERY,
                TOOL_CODE_STRUCTURE_ANALYZER,
                TOOL_MODEL_GATEWAY,
                TOOL_PATCH_PROPOSAL_WRITER,
            }
        ),
        autonomy_level=2,
        agents=("architecture_node",),
        success_conditions=(
            "architecture_diagram_produced == true",
            "stream_a_style_alignment == true",
        ),
        description=(
            "Handles system design, dependency evaluation, and architectural "
            "trade-off analysis. Scoped to Streams A, D, and B."
        ),
    ),
    Department.SECURITY: _sandbox(
        department=Department.SECURITY,
        streams=frozenset(
            {
                COLLECTION_TECHNICAL_MASTERY,
                COLLECTION_AMBIENT_TELEMETRY,
            }
        ),
        tools=frozenset(
            {
                TOOL_CHROMA_QUERY,
                TOOL_SECURITY_STATIC_SCAN,
                TOOL_GIT_PIPELINE,
            }
        ),
        autonomy_level=1,
        agents=("security_scanner",),
        success_conditions=(
            "static_analysis_clean == true",
            "no_plaintext_secrets_detected == true",
        ),
        description=(
            "Handles security scanning, vulnerability analysis, and "
            "compliance checks. Scoped to Streams B and C."
        ),
    ),
    Department.MEMORY_INDEXING: _sandbox(
        department=Department.MEMORY_INDEXING,
        streams=frozenset(
            {
                COLLECTION_COGNITIVE_IDENTITY,
                COLLECTION_CODE_TOPOLOGIES,
                COLLECTION_TECHNICAL_MASTERY,
                COLLECTION_AMBIENT_TELEMETRY,
            }
        ),
        tools=frozenset(
            {
                TOOL_CHROMA_QUERY,
                TOOL_FILE_WATCHER,
                TOOL_GIT_PIPELINE,
                TOOL_INGESTION_COORDINATOR,
            }
        ),
        autonomy_level=0,
        agents=("indexing_daemon",),
        success_conditions=(
            "vector_index_updated == true",
            "zero_collection_bleed == true",
        ),
        description=(
            "Handles memory ingestion, re-indexing, and reflection loop "
            "operations. Scoped to all four Streams. Observe-only autonomy."
        ),
    ),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_sandbox(department: Department) -> DepartmentWorkerSandbox:
    """
    Look up the sandbox configuration for a given department.

    Parameters
    ----------
    department : Department

    Returns
    -------
    DepartmentWorkerSandbox

    Raises
    ------
    KeyError
        If the department is not in DEPARTMENT_REGISTRY (should never happen
        for valid Department enum members, but guards against future gaps).
    """
    return DEPARTMENT_REGISTRY[department]


def department_from_string(value: str) -> Department:
    """
    Convert a raw string from the model response to a ``Department`` enum member.

    Strips whitespace and lowercases before matching.

    Parameters
    ----------
    value : str

    Returns
    -------
    Department

    Raises
    ------
    ValueError
        If ``value`` does not match any department.
    """
    normalised = value.strip().lower()
    for member in Department:
        if member.value == normalised:
            return member
    raise ValueError(
        f"department_from_string: '{value}' is not a valid department. "
        f"Valid values: {[m.value for m in Department]}"
    )


__all__ = [
    "Department",
    "DepartmentWorkerSandbox",
    "ALL_WORKER_TOOLS",
    "TOOL_CHROMA_QUERY",
    "TOOL_CODE_STRUCTURE_ANALYZER",
    "TOOL_STYLE_FINGERPRINT_EXTRACTOR",
    "TOOL_GIT_PIPELINE",
    "TOOL_FILE_WATCHER",
    "TOOL_INGESTION_COORDINATOR",
    "TOOL_MODEL_GATEWAY",
    "TOOL_SECURITY_STATIC_SCAN",
    "TOOL_PATCH_PROPOSAL_WRITER",
    "TOOL_STRATEGIC_SUMMARY_BUILDER",
    "DEPARTMENT_REGISTRY",
    "get_sandbox",
    "department_from_string",
]
