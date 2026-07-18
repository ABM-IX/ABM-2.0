"""
abm/memory/chunking.py
=====================
Chunking helpers for ABM memory Streams A, B, and C.

The implementations follow ABM_SPEC.md section 3:
  - Stream A: AST-boundary / structural code chunks, never mid-line.
  - Stream B: recursive token chunks, 500-token window, 50-token overlap.
  - Stream C: chronological windows split on 120-second interaction gaps.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Mapping, Sequence
from typing import Any


STREAM_B_TOKEN_WINDOW = 500
STREAM_B_TOKEN_OVERLAP = 50
STREAM_C_INTERACTION_GAP_SECONDS = 120


def chunk_stream_a_code_topologies(code: str, language: str) -> list[str]:
    """
    Chunk Stream A code on AST or structural boundaries.

    Python code is split by top-level AST node boundaries. Dart and Kotlin use
    brace-depth structural boundaries. All paths split only on line boundaries,
    so code is never split mid-line.
    """
    if not code.strip():
        return []

    if language == "python":
        try:
            return _chunk_python_ast_boundaries(code)
        except SyntaxError:
            return _chunk_by_structural_lines(code)

    if language in {"dart", "kotlin"}:
        return _chunk_by_structural_lines(code)

    raise ValueError("language must be one of: dart, kotlin, python")


def chunk_stream_b_technical_mastery(
    text: str,
    *,
    token_window: int = STREAM_B_TOKEN_WINDOW,
    token_overlap: int = STREAM_B_TOKEN_OVERLAP,
) -> list[str]:
    """
    Chunk Stream B text into recursive token windows.

    The default contract is a 500-token window with 50-token overlap.
    """
    if token_window <= 0:
        raise ValueError("token_window must be greater than 0")
    if token_overlap < 0:
        raise ValueError("token_overlap must be greater than or equal to 0")
    if token_overlap >= token_window:
        raise ValueError("token_overlap must be smaller than token_window")

    tokens = _recursive_tokens(text)
    if not tokens:
        return []

    chunks: list[str] = []
    step = token_window - token_overlap
    for start in range(0, len(tokens), step):
        window = tokens[start : start + token_window]
        if not window:
            break
        chunks.append(" ".join(window))
        if start + token_window >= len(tokens):
            break
    return chunks


def chunk_stream_c_ambient_telemetry(
    events: Sequence[Mapping[str, Any]],
    *,
    gap_seconds: int = STREAM_C_INTERACTION_GAP_SECONDS,
) -> list[list[dict[str, Any]]]:
    """
    Chunk Stream C telemetry into chronological windows.

    Events are sorted by ``epoch_timestamp`` and a new block starts whenever
    the gap between adjacent events is greater than 120 seconds by default.
    """
    if gap_seconds < 0:
        raise ValueError("gap_seconds must be greater than or equal to 0")
    if not events:
        return []

    sorted_events = sorted(
        (dict(event) for event in events),
        key=lambda event: _event_timestamp(event),
    )

    windows: list[list[dict[str, Any]]] = []
    current_window: list[dict[str, Any]] = [sorted_events[0]]

    for event in sorted_events[1:]:
        previous_timestamp = _event_timestamp(current_window[-1])
        current_timestamp = _event_timestamp(event)
        if current_timestamp - previous_timestamp > gap_seconds:
            windows.append(current_window)
            current_window = [event]
        else:
            current_window.append(event)

    windows.append(current_window)
    return windows


def _chunk_python_ast_boundaries(code: str) -> list[str]:
    lines = code.splitlines()
    tree = ast.parse(code)
    if not tree.body:
        return [code]

    chunks: list[str] = []
    cursor = 1
    for node in tree.body:
        start = _node_start_lineno(node)
        end = getattr(node, "end_lineno", None) or start
        chunk_start = cursor if cursor < start else start
        chunk = "\n".join(lines[chunk_start - 1 : end]).strip("\n")
        if chunk.strip():
            chunks.append(chunk)
        cursor = end + 1

    if cursor <= len(lines):
        tail = "\n".join(lines[cursor - 1 :]).strip("\n")
        if tail.strip():
            chunks.append(tail)
    return chunks


def _node_start_lineno(node: ast.AST) -> int:
    decorator_lines = [
        decorator.lineno
        for decorator in getattr(node, "decorator_list", [])
        if hasattr(decorator, "lineno")
    ]
    node_lineno = getattr(node, "lineno", 1)
    return min([node_lineno, *decorator_lines])


def _chunk_by_structural_lines(code: str) -> list[str]:
    chunks: list[str] = []
    current_lines: list[str] = []
    brace_depth = 0

    for line in code.splitlines():
        stripped = line.strip()
        current_lines.append(line)
        brace_depth += line.count("{") - line.count("}")

        boundary = (
            bool(stripped)
            and brace_depth <= 0
            and (stripped.endswith("}") or stripped.endswith(";"))
        )
        if boundary:
            chunk = "\n".join(current_lines).strip("\n")
            if chunk.strip():
                chunks.append(chunk)
            current_lines = []
            brace_depth = 0

    if current_lines:
        chunk = "\n".join(current_lines).strip("\n")
        if chunk.strip():
            chunks.append(chunk)

    return chunks


def _recursive_tokens(text: str) -> list[str]:
    paragraph_chunks = [chunk for chunk in re.split(r"\n\s*\n", text) if chunk.strip()]
    tokens: list[str] = []
    for paragraph in paragraph_chunks:
        sentence_chunks = re.split(r"(?<=[.!?])\s+", paragraph.strip())
        for sentence in sentence_chunks:
            tokens.extend(sentence.split())
    return tokens


def _event_timestamp(event: Mapping[str, Any]) -> int:
    timestamp = event.get("epoch_timestamp")
    if not isinstance(timestamp, int):
        raise ValueError("each event must include int epoch_timestamp")
    return timestamp


__all__ = [
    "STREAM_B_TOKEN_WINDOW",
    "STREAM_B_TOKEN_OVERLAP",
    "STREAM_C_INTERACTION_GAP_SECONDS",
    "chunk_stream_a_code_topologies",
    "chunk_stream_b_technical_mastery",
    "chunk_stream_c_ambient_telemetry",
]
