"""
abm/api/__init__.py
====================
ABM API Layer — Phase v1.0

Re-exports the complete public surface of the API layer.  Clients import
from here; they never reach into ``abm.api.core`` or ``abm.api.capabilities``
directly.

Architectural Constitution rule 13: all clients communicate exclusively
through this layer.  No client owns memory, planning, reflection, routing,
or reasoning.
"""

from abm.api.capabilities import (
    AnswerResult,
    ExplainResult,
    KnowledgeResult,
    MemoryResult,
    StatusResult,
    AmbientIngestionResult,
    aggregateProjectMemory,
    answerQuestion,
    continueTask,
    explainAuditRecord,
    getSystemStatus,
    ingestAmbientEvent,
    learnTopic,
    planProject,
    reflectOnWork,
    retrieveKnowledge,
    summarizeProject,
)
from abm.api.core.config import APIConfig
from abm.api.core.registry import HealthStatus, ServiceRegistry

__all__ = [
    # Core lifecycle
    "APIConfig",
    "ServiceRegistry",
    "HealthStatus",
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
    # Future capabilities (stubs — NotImplementedError until backend is gated)
    "continueTask",
    "reflectOnWork",
    "planProject",
    "learnTopic",
]
