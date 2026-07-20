"""
abm/clients/console/formatter.py
==================================
Terminal output formatters for the ABM console client.

Converts API return types into readable, well-structured terminal output.
Contains zero cognitive logic — it formats, never reasons.

Design contract:
  - Every formatter accepts one API result object and returns a ``str``.
  - Formatters never call into the API layer or ServiceRegistry.
  - Formatters never raise — they produce a fallback message on bad input.
"""

from __future__ import annotations

from typing import Any

from abm.api.capabilities import (
    AnswerResult,
    ExplainResult,
    KnowledgeResult,
    MemoryResult,
    StatusResult,
)
from abm.memory.chroma_controller import (
    COLLECTION_AMBIENT_TELEMETRY,
    COLLECTION_CODE_TOPOLOGIES,
    COLLECTION_COGNITIVE_IDENTITY,
    COLLECTION_TECHNICAL_MASTERY,
)
from abm.strategic_wing.strategic_asset_analyzer import StrategicAnalysisResult

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

_DIVIDER = "─" * 60
_STREAM_LABELS: dict[str, str] = {
    COLLECTION_COGNITIVE_IDENTITY: "Stream D — Identity & Decisions",
    COLLECTION_CODE_TOPOLOGIES: "Stream A — Code Topologies",
    COLLECTION_TECHNICAL_MASTERY: "Stream B — Technical Mastery",
    COLLECTION_AMBIENT_TELEMETRY: "Stream C — Ambient Telemetry",
}
_MAX_SNIPPET = 280  # characters shown per hit


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────


def _snippet(text: str, max_chars: int = _MAX_SNIPPET) -> str:
    """Truncate text to ``max_chars``, appending '…' if truncated."""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + " …"


def _distance_bar(distance: float | None, width: int = 20) -> str:
    """Visualise semantic distance as an ASCII relevance bar."""
    if distance is None:
        return " " * width
    # Clamp: chromadb cosine distances in [0, 2]; treat ≥1.5 as "far"
    relevance = max(0.0, min(1.0, 1.0 - distance / 1.5))
    filled = round(relevance * width)
    return "█" * filled + "░" * (width - filled)


def _format_hit(hit: dict[str, Any], index: int) -> str:
    """Format a single retrieval hit."""
    dist = hit.get("distance")
    dist_str = f"{dist:.4f}" if dist is not None else "n/a"
    bar = _distance_bar(dist)
    collection = hit.get("collection", "unknown")
    label = _STREAM_LABELS.get(collection, collection)
    text = _snippet(hit.get("text", ""))
    lines = [
        f"  [{index + 1}] {label}",
        f"      Relevance: {bar} (distance={dist_str})",
    ]
    if text:
        # Indent text block
        indented = "\n".join(f"      {line}" for line in text.splitlines())
        lines.append(indented)
    return "\n".join(lines)


def _degraded_warning(command: str) -> str:
    return (
        f"\n  ⚠  Ollama is not reachable. '{command}' results may be incomplete.\n"
        "      Ensure the local Ollama server is running at 127.0.0.1:11434.\n"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Public formatters
# ──────────────────────────────────────────────────────────────────────────────


def format_ask(result: AnswerResult) -> str:
    """Format the output of ``answerQuestion`` for terminal display."""
    lines = [
        _DIVIDER,
        f"  ABM › ask",
        f"  Question : {result.question}",
        f"  Routed to: {result.department}  (confidence: {result.confidence})",
    ]
    if result.fallback_used:
        lines.append("  ℹ  Router used fallback department (Ollama may be unavailable).")
    lines.append(_DIVIDER)

    if result.degraded:
        lines.append(_degraded_warning("ask"))

    if not result.hits:
        lines.append("\n  No relevant memory found for this question.\n")
    else:
        lines.append(f"\n  {len(result.hits)} memory hit(s):\n")
        for i, hit in enumerate(result.hits):
            lines.append(_format_hit(hit, i))
            lines.append("")

    lines.append(_DIVIDER)
    return "\n".join(lines)


def format_search(result: KnowledgeResult) -> str:
    """Format the output of ``retrieveKnowledge`` for terminal display."""
    lines = [
        _DIVIDER,
        f"  ABM › search",
        f"  Query: {result.query}",
        _DIVIDER,
    ]

    if result.degraded:
        lines.append(_degraded_warning("search"))

    if not result.hits:
        lines.append("\n  No results found.\n")
    else:
        lines.append(f"\n  {len(result.hits)} result(s) across all streams:\n")
        for i, hit in enumerate(result.hits):
            lines.append(_format_hit(hit, i))
            lines.append("")

    lines.append(_DIVIDER)
    return "\n".join(lines)


def format_status(result: StatusResult) -> str:
    """Format the output of ``getSystemStatus`` for terminal display."""
    health_icon = "✓" if not result.degraded else "⚠"
    ollama_icon = "✓" if result.ollama_reachable else "✗"
    chroma_icon = "✓" if result.chroma_ready else "✗"

    lines = [
        _DIVIDER,
        "  ABM › status",
        _DIVIDER,
        f"  System Health : {health_icon} {'OK' if not result.degraded else 'DEGRADED'}",
        f"    Ollama      : {ollama_icon} {'reachable' if result.ollama_reachable else 'not reachable (127.0.0.1:11434)'}",
        f"    ChromaDB    : {chroma_icon} {'ready' if result.chroma_ready else 'not ready'}",
        "",
        "  Workflow Overview:",
        "",
    ]
    for line in result.overview.splitlines():
        lines.append(f"  {line}")

    if result.quarantined_ids:
        lines.append("")
        lines.append(f"  Quarantined (on disk): {', '.join(result.quarantined_ids)}")

    lines.append(_DIVIDER)
    return "\n".join(lines)


def format_summarize(result: StrategicAnalysisResult) -> str:
    """Format the output of ``summarizeProject`` for terminal display."""
    lines = [
        _DIVIDER,
        "  ABM › summarize",
        f"  Project: {result.query}",
        _DIVIDER,
        f"\n  {len(result.context_items)} memory item(s) retrieved across all streams.",
        f"  {len(result.options)} strategic option path(s) identified:\n",
    ]

    for i, opt in enumerate(result.options, 1):
        streams_str = ", ".join(opt.supporting_streams) if opt.supporting_streams else "—"
        lines.append(f"  [{i}] {opt.title}")
        lines.append(f"      Streams  : {streams_str}")
        lines.append(f"      Rationale: {_snippet(opt.rationale, 200)}")
        if opt.tradeoffs:
            lines.append("      Trade-offs:")
            for t in opt.tradeoffs:
                lines.append(f"        • {t}")
        if opt.next_questions:
            lines.append("      Next questions:")
            for q in opt.next_questions:
                lines.append(f"        ? {q}")
        lines.append("")

    lines.append(_DIVIDER)
    return "\n".join(lines)


def format_memory(result: MemoryResult) -> str:
    """Format the output of ``aggregateProjectMemory`` for terminal display."""
    lines = [
        _DIVIDER,
        "  ABM › memory",
        f"  Project: {result.project_name}",
        _DIVIDER,
    ]

    if result.degraded:
        lines.append(_degraded_warning("memory"))

    if result.total_hits == 0:
        lines.append("\n  No memory found for this project.\n")
    else:
        lines.append(f"\n  {result.total_hits} total memory item(s):\n")
        for collection_name, hits in result.streams.items():
            label = _STREAM_LABELS.get(collection_name, collection_name)
            if not hits:
                continue
            lines.append(f"  ┌ {label} ({len(hits)} item(s))")
            for i, hit in enumerate(hits):
                dist = hit.get("distance")
                dist_str = f"{dist:.4f}" if dist is not None else "n/a"
                text = _snippet(hit.get("text", ""), 200)
                lines.append(f"  │  [{i + 1}] distance={dist_str}")
                if text:
                    for tl in text.splitlines():
                        lines.append(f"  │       {tl}")
            lines.append("  └")
            lines.append("")

    lines.append(_DIVIDER)
    return "\n".join(lines)


def format_explain(result: ExplainResult) -> str:
    """Format the output of ``explainAuditRecord`` for terminal display."""
    lines = [
        _DIVIDER,
        "  ABM › explain",
        f"  Target: {result.target}",
        _DIVIDER,
        f"\n  {result.notes}\n",
    ]

    if not result.found:
        lines.append(_DIVIDER)
        return "\n".join(lines)

    for i, rec in enumerate(result.records, 1):
        source = rec.get("source", "unknown")
        lines.append(f"  ── Record [{i}] source={source} ──────────────────")

        if source == "monitor":
            lines.append(f"    Contract ID : {rec.get('contract_id', '?')}")
            lines.append(f"    Objective   : {_snippet(rec.get('objective', ''), 120)}")
            lines.append(f"    Department  : {rec.get('department', '?')}")
            lines.append(f"    State       : {rec.get('state', '?')}")
            if "gate_passed" in rec:
                passed_icon = "✓ PASSED" if rec["gate_passed"] else "✗ FAILED"
                lines.append(f"    Gate        : {passed_icon}")
                lines.append(f"    Confidence  : {rec.get('confidence_score', '?')}")
                lines.append(f"    Quarantined : {rec.get('quarantine_flag', False)}")
                if rec.get("gate_reason"):
                    lines.append(f"    Gate reason : {rec['gate_reason']}")
            if "exit_code" in rec:
                lines.append(f"    Exit code   : {rec['exit_code']}")
                lines.append(f"    Exec time   : {rec.get('execution_time_ms', '?')}ms")

        elif source == "decision_journal":
            lines.append(f"    Doc ID      : {rec.get('doc_id', '?')}")
            dist = rec.get("distance")
            dist_str = f"{dist:.4f}" if dist is not None else "n/a"
            lines.append(f"    Distance    : {dist_str}")
            text = _snippet(rec.get("text", ""), 400)
            if text:
                lines.append("    Content:")
                for tl in text.splitlines():
                    lines.append(f"      {tl}")
        lines.append("")

    lines.append(_DIVIDER)
    return "\n".join(lines)
