"""
abm/strategic_wing/strategic_asset_analyzer.py
==============================================
Strategic asset analyzer for Phase v0.5.

Maps company-direction questions to option sets using existing memory streams.
This module is analysis-only: it never writes to memory and never records
decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from abm.api.core.interfaces import EmbedderInterface, VectorStoreInterface
from abm.memory.chroma_controller import (
    ALL_COLLECTIONS,
    COLLECTION_AMBIENT_TELEMETRY,
    COLLECTION_CODE_TOPOLOGIES,
    COLLECTION_COGNITIVE_IDENTITY,
    COLLECTION_TECHNICAL_MASTERY,
    QueryResult,
)


STREAM_LABELS: dict[str, str] = {
    COLLECTION_COGNITIVE_IDENTITY: "Stream D",
    COLLECTION_CODE_TOPOLOGIES: "Stream A",
    COLLECTION_TECHNICAL_MASTERY: "Stream B",
    COLLECTION_AMBIENT_TELEMETRY: "Stream C",
}


@dataclass(frozen=True)
class StrategicContextItem:
    """One retrieved memory item used as evidence for strategic analysis."""

    collection_name: str
    document_id: str
    text: str
    metadata: dict[str, Any]
    distance: float | None = None


@dataclass(frozen=True)
class StrategicOption:
    """One mapped-out strategic path. Not a decision or recommendation."""

    title: str
    rationale: str
    supporting_streams: list[str]
    evidence: list[StrategicContextItem] = field(default_factory=list)
    tradeoffs: list[str] = field(default_factory=list)
    next_questions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class StrategicAnalysisResult:
    """Read-only output from a StrategicAssetAnalyzer query."""

    query: str
    context_items: list[StrategicContextItem]
    options: list[StrategicOption]
    decision_recorded: bool = False


class StrategicAssetAnalyzer:
    """
    Read-side analyzer that maps company-direction queries into option sets.

    It retrieves context through ChromaController.query_collection() only.
    It does not call ChromaController.add_document(), DecisionJournal, or any
    other persistence API.
    """

    def __init__(
        self,
        controller: VectorStoreInterface,
        embedder: EmbedderInterface,
        collections: tuple[str, ...] = ALL_COLLECTIONS,
    ) -> None:
        self.controller = controller
        self.embedder = embedder
        self.collections = collections

    def analyze(
        self, query: str, n_results_per_stream: int = 3
    ) -> StrategicAnalysisResult:
        """Return mapped strategic options for a company-direction query."""
        if not query or not query.strip():
            raise ValueError("query must be a non-empty string.")
        if n_results_per_stream < 1:
            raise ValueError("n_results_per_stream must be at least 1.")

        context_items = self.retrieve_context(query, n_results_per_stream)
        options = self.map_options(query, context_items)
        return StrategicAnalysisResult(
            query=query,
            context_items=context_items,
            options=options,
            decision_recorded=False,
        )

    def retrieve_context(
        self, query: str, n_results_per_stream: int = 3
    ) -> list[StrategicContextItem]:
        """Embed the query and retrieve relevant context from configured streams."""
        if not query or not query.strip():
            raise ValueError("query must be a non-empty string.")
        if n_results_per_stream < 1:
            raise ValueError("n_results_per_stream must be at least 1.")

        query_embedding = self.embedder.embed(query)
        context_items: list[StrategicContextItem] = []

        for collection_name in self.collections:
            result = self.controller.query_collection(
                collection_name=collection_name,
                query_embedding=query_embedding,
                n_results=n_results_per_stream,
            )
            context_items.extend(self._flatten_query_result(result))

        return sorted(
            context_items,
            key=lambda item: float("inf") if item.distance is None else item.distance,
        )

    def map_options(
        self, query: str, context_items: list[StrategicContextItem]
    ) -> list[StrategicOption]:
        """Turn retrieved stream evidence into analysis-only strategic paths."""
        grouped = self._group_by_collection(context_items)
        options: list[StrategicOption] = []

        if COLLECTION_COGNITIVE_IDENTITY in grouped:
            evidence = grouped[COLLECTION_COGNITIVE_IDENTITY]
            options.append(
                StrategicOption(
                    title="Mission-aligned path",
                    rationale=(
                        "Use Stream D identity, goals, and FirstMinds philosophy "
                        f"as the primary lens for '{query}'."
                    ),
                    supporting_streams=[STREAM_LABELS[COLLECTION_COGNITIVE_IDENTITY]],
                    evidence=evidence,
                    tradeoffs=[
                        "Strong continuity with corporate intent.",
                        "May underweight near-term implementation constraints.",
                    ],
                    next_questions=[
                        "Which identity principle is non-negotiable for this direction?",
                        "What outcome would make this path clearly aligned with FirstMinds?",
                    ],
                )
            )

        if COLLECTION_CODE_TOPOLOGIES in grouped:
            evidence = grouped[COLLECTION_CODE_TOPOLOGIES]
            options.append(
                StrategicOption(
                    title="Architecture-aligned build path",
                    rationale=(
                        "Use Stream A engineering patterns and architecture signals "
                        "to shape an implementation direction."
                    ),
                    supporting_streams=[STREAM_LABELS[COLLECTION_CODE_TOPOLOGIES]],
                    evidence=evidence,
                    tradeoffs=[
                        "Keeps the path close to proven technical habits.",
                        "Can bias toward familiar architecture even when strategy shifts.",
                    ],
                    next_questions=[
                        "Which existing architecture pattern best supports the query?",
                        "What technical pattern should be avoided because it conflicts with the goal?",
                    ],
                )
            )

        if COLLECTION_TECHNICAL_MASTERY in grouped:
            evidence = grouped[COLLECTION_TECHNICAL_MASTERY]
            options.append(
                StrategicOption(
                    title="Validated-asset path",
                    rationale=(
                        "Use Stream B validated technical assets to reduce unknowns "
                        "before committing to a direction."
                    ),
                    supporting_streams=[STREAM_LABELS[COLLECTION_TECHNICAL_MASTERY]],
                    evidence=evidence,
                    tradeoffs=[
                        "Improves technical confidence before execution.",
                        "May slow momentum while validation gaps are closed.",
                    ],
                    next_questions=[
                        "Which technical asset is strongest evidence for this option?",
                        "What missing validation would block execution?",
                    ],
                )
            )

        if COLLECTION_AMBIENT_TELEMETRY in grouped:
            evidence = grouped[COLLECTION_AMBIENT_TELEMETRY]
            options.append(
                StrategicOption(
                    title="Workflow-timed path",
                    rationale=(
                        "Use Stream C recent workflow and interaction context to "
                        "time the direction around current execution load."
                    ),
                    supporting_streams=[STREAM_LABELS[COLLECTION_AMBIENT_TELEMETRY]],
                    evidence=evidence,
                    tradeoffs=[
                        "Grounds strategy in current operating reality.",
                        "Recent activity can overweight temporary urgency.",
                    ],
                    next_questions=[
                        "Which in-flight activity would this direction unblock?",
                        "What should pause before this path starts?",
                    ],
                )
            )

        if not options:
            options.append(
                StrategicOption(
                    title="Evidence-gathering path",
                    rationale=(
                        "No matching memory context was retrieved, so the analysis "
                        "should stay exploratory until stronger evidence exists."
                    ),
                    supporting_streams=[],
                    evidence=[],
                    tradeoffs=[
                        "Avoids inventing direction from weak context.",
                        "Requires more memory ingestion or manual context before action.",
                    ],
                    next_questions=[
                        "Which Stream D goal or FirstMinds principle should be added?",
                        "Which technical or workflow evidence would clarify the path?",
                    ],
                )
            )

        return options

    @staticmethod
    def _flatten_query_result(result: QueryResult) -> list[StrategicContextItem]:
        items: list[StrategicContextItem] = []
        ids = result.ids[0] if result.ids else []
        documents = result.documents[0] if result.documents else []
        metadatas = result.metadatas[0] if result.metadatas else []
        distances = result.distances[0] if result.distances else []

        for index, document_id in enumerate(ids):
            text = documents[index] if index < len(documents) else ""
            metadata = metadatas[index] if index < len(metadatas) else {}
            distance = distances[index] if index < len(distances) else None
            items.append(
                StrategicContextItem(
                    collection_name=result.collection_name,
                    document_id=document_id,
                    text=text,
                    metadata=dict(metadata),
                    distance=distance,
                )
            )

        return items

    @staticmethod
    def _group_by_collection(
        context_items: list[StrategicContextItem],
    ) -> dict[str, list[StrategicContextItem]]:
        grouped: dict[str, list[StrategicContextItem]] = {}
        for item in context_items:
            grouped.setdefault(item.collection_name, []).append(item)
        return grouped
